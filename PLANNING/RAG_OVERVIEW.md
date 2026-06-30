# RAG_OVERVIEW.md — Agentic RAG · gnosis-chat
> **Documento de Design Arquitetural e Brainstorm**
> Sistema RAG Avançado com Agentes Especializados
>
> _Última atualização: 19 Abr 2026 · Status: 🟢 Todas as Decisões Fechadas — Pronto para Implementação_

---

## Índice

1. [Project Context](#1-project-context)
2. [Framework Agêntico](#2-framework-agêntico)
3. [Topologia de Agentes](#3-topologia-de-agentes)
4. [Mecânicas do Researcher](#4-mecânicas-do-researcher)
5. [Mecânicas do Planner](#5-mecânicas-do-planner)
6. [Observabilidade e Resiliência](#6-observabilidade-e-resiliência)
7. [Log de Decisões Técnicas](#7-log-de-decisões-técnicas)
8. [Próximos Passos](#8-próximos-passos)

---

## 1. Project Context

> 🟢 **Decidido** — contexto consolidado a partir do SSOT do projeto

### O que é o gnosis-chat

**gnosis-chat** é uma aplicação mobile de chat inteligente com base de conhecimento gnóstica. O backend em Python (FastAPI + LangGraph) expõe uma API de conversação que usa RAG sobre um corpus de PDFs doutrinários (~148 livros indexados em Qdrant via LlamaIndex + Gemini Embeddings).

### Stack atual relevante

| Componente | Tecnologia |
|---|---|
| Web Framework | FastAPI 0.115+ / Uvicorn |
| Vector Store | Qdrant (AsyncQdrantClient) |
| Embeddings | Google Gemini `models/embedding-001` via LlamaIndex |
| LLM | Google Gemini Flash (routing + síntese) |
| Agentic Framework | **LangGraph** (instalado, pipeline stub existente) |
| Observabilidade | LangSmith (tracing_v2 configurado) |
| Auth | Supabase JWT |
| PDF Pipeline | unstructured[pdf] + YOLOX hi_res + PyMuPDF + pytesseract |

> ⚠️ **Nota Crítica de Contexto:** LangGraph já está instalado no `pyproject.toml` e existe um stub de `StateGraph` com `pipeline.py`, `state.py` e `retriever.py`. Qualquer mudança de framework tem custo de migração real.

---

## 2. Framework Agêntico

> 🟢 **Decidido**

### Candidatos

| Framework | Paradigma | Maturidade |
|---|---|---|
| **LangGraph** | Grafo de estados tipado (state machine) | Alta — LangChain Inc., amplamente adotado |
| **CrewAI** | Role-based, multi-agent declarativo | Média — crescimento rápido, API mais simples |
| **smolagents** (HuggingFace) | Code-first, LLM escreve e executa Python | Baixa/Experimental — poder alto, risco alto |

### Trade-offs documentados

| Dimensão | LangGraph ✅ | CrewAI ❌ | smolagents ❌ |
|---|---|---|---|
| Fan-out dinâmico de agentes | `Send` API nativo | Limitado, workarounds necessários | Não aplicável |
| Loop Critic → Planner | Edge condicional explícita | Opaco, difícil de controlar | Não aplicável |
| Human-in-the-Loop | `interrupt_before` nativo | Suporte parcial | Não aplicável |
| Custo de implementação | Alto (plumbing explícito) | Baixo (declarativo) | — |
| Integração com stack existente | ✅ Já instalado + LangSmith wired | ❌ Migração necessária | ❌ Descartado |

### Decisão

> 🟢 **Decidido** — **LangGraph**
>
> Planner com **topologia dinâmica em runtime** (Opção A): o Planner decide quantos Researchers despachar e com quais sub-queries a cada invocação, usando o `Send` API do LangGraph para fan-out concorrente. O número máximo é de 6 Researchers globais (exemplo: 4 iniciais + 2 pré-requisitos).

---

## 3. Topologia de Agentes

> 🟢 **Decidido**

### Papéis propostos

| Agente | Responsabilidade | Limites |
|---|---|---|
| **Planner** | Decompõe a query, despacha Researchers, verifica checklist | Não acessa vector store diretamente |
| **Researcher** | Única entidade autorizada a executar RAG | Não escreve resposta final |
| **Writer** | Sintetiza os resultados dos Researchers em resposta coesa | Não faz busca |
| **Summarizer** | Cria um resumo (Recap/TL;DR) da resposta final aprovada usando Gemini 3.0 Flash Lite | Não altera a resposta principal, não faz busca |
| **Critic** | Avalia qualidade, coerência e fundamentação da resposta | Pode solicitar nova rodada |
| **Judge** _(opcional)_ | Árbitro final entre Critic e Writer em caso de conflito | A decidir se necessário |

### Fluxo Proposto (rascunho)

```
User Query
    └─> Planner (decomposição + checklist)
            ├─> Researcher A (query X) ─┐
            ├─> Researcher B (query Y) ─┼─> Writer (síntese)
            └─> Researcher C (query Z) ─┘        └─> Critic (revisão)
                                                          └─> [aprovado] → Resposta Final
                                                          └─> [rejeitado] → Planner (revisão)
```

### Topologia finalizada — com circuit breaker e roteamento inteligente

```
User Query
    └─> Planner (classificação de intent + decomposição + checklist)
         │
         ├─ [query_type = "conversational"] ──────────────→ Resposta Direta (sem RAG)
         │
         ├─ [query_type = "knowledge_query"]
         │   │   [clarity_score < 3?] → HITL: pergunta esclarecedora ao usuário
         │   │
         │   ├─> Researcher A (sub-query X) ─┐  ← synonym expansion interna
         │   ├─> Researcher B (sub-query Y) ─┼─ [paralelo via Send API]
         │   └─> Researcher C (sub-query Z) ─┘  ← cada Researcher expande sua sub-query
         │              │
         │              ▼
         │         Writer (síntese)
         │              │
         │              ▼
         │         Critic (revisão — com rejection_type)
         │          ├─ [aprovado] ────────────────────────────────────→ Summarizer (recap) → Resposta Final
         │          ├─ [poor_writing] ───────────────────────────────→ Writer (rewrite, SEM pesquisa)
         │          ├─ [missing_prerequisite] → Planner (pesquisa ADICIONAL de pré-requisitos)
         │          │       └─> Researcher N (conceito X) ─→ agrega ao estado existente
         │          │                   └─→ Writer (resintetiza: pré-requisito + resposta original)
         │          ├─ [insufficient_content, tentativa 1] → Planner (nova pesquisa completa)
         │          └─ [qualquer rejeição, tentativa 2+] ──→ Judge (circuit breaker)
         │                       ├─ [aprovar com ressalvas] → Summarizer (recap) → Resposta Final
         │                       ├─ [nova pesquisa profunda] → Planner
         │                       └─ [não encontrado] → Resposta de fallback
```

> **Nota sobre synonym expansion:** O Planner decompõe a query em sub-queries semânticas. Cada Researcher recebe UMA sub-query e internamente realiza a synonym expansion + query rewrite **antes** de consultar o Qdrant. O Planner não conhece os termos expandidos — só as sub-queries de alto nível.

### Contrato de estado do Researcher (definido)

```python
# Cada Researcher devolve ao estado pai (agregado via reducer):
ResearcherOutput = {
    "sub_query": str,           # a query que recebeu do Planner
    "retrieved_docs": list,     # chunks pós re-rank (top K)
    "source_citations": list,   # metadados: autor, livro, câmara, página
    "confidence_score": float,  # sinal quantitativo de qualidade para o Critic
}
```

### Contrato de output do Writer (definido)

```python
WriterOutput = {
    "content": str,          # resposta em Markdown (estrutura adaptativa — ver abaixo)
    "response_type": str,    # "simple" | "structured"
    "cited_sources": list,   # lista de source_citations usadas na resposta
}
```

**Estrutura Markdown adaptativa por complexidade:**

| Cenário | `response_type` | Estrutura gerada |
|---|---|---|
| Query simples, 1 Researcher | `"simple"` | Texto corrido com **bold** em termos-chave. Sem headers. |
| Query multi-tópico (2+ Researchers) | `"structured"` | Seção `##` por tópico + `---` + `**Fontes:**` no rodapé |
| Ciclo `missing_prerequisite` | `"structured"` | `## Conceito Base: X` primeiro, depois `## Resposta: Y` |

**Exemplo de resposta structured (multi-tópico com pré-requisito):**

```markdown
## Conceito Base: O que é o Kundartiguador
O Kundartiguador é o órgão do pecado segundo a doutrina gnóstica...

## O Papel do Kundartiguador na Alquimia Sexual
Uma vez compreendido o conceito, sua relação com a transmutação...

---
**Fontes:**
- *Tratado de Alquimia Sexual* — V.M. Samael Aun Weor (1ª Câmara, p. 42)
- *O Matrimônio Perfeito* — V.M. Samael Aun Weor (1ª Câmara, p. 15)
```

> **Nota de implementação frontend:** O app Flutter precisa de `flutter_markdown` para renderizar o output do Writer. O `response_type` pode ser usado pelo frontend para alternar entre render Markdown vs. texto simples se necessário.

### Contratos de output dos agentes principais

```python
# Critic — retorna rejection_type para roteamento inteligente
CriticOutput = {
    "approved": bool,
    "rejection_type": str | None,        # "poor_writing" | "insufficient_content"
                                         # | "missing_prerequisite" | None
    "feedback": str,                     # instrução específica para Writer ou Planner
    "prerequisite_concepts": list[str],  # conceitos pré-requisito identificados
                                         # (só preenchido se "missing_prerequisite")
    "revision_count": int                # incrementado a cada rejeição
}
```

> **Roteamento do Critic — 4 caminhos:**
>
> | `rejection_type` | Destino | O que acontece | Custo |
> |---|---|---|---|
> | `None` (aprovado) | Resposta Final | Pipeline encerrado | — |
> | `"poor_writing"` | **Writer** | Reescrita com `feedback`. Zero Qdrant. | 1 LLM call |
> | `"insufficient_content"` | **Planner** | Novo ciclo de pesquisa completo sobre a query original | Qdrant + Vertex AI |
> | `"missing_prerequisite"` | **Planner** | Pesquisa ADICIONAL sobre `prerequisite_concepts`; resultados anteriores são **preservados** | Qdrant + Vertex AI (só para os pré-requisitos) |
> | qualquer, `revision_count >= 2` | **Judge** | Circuit breaker | 1 LLM call |
>
> **Detalhe do `missing_prerequisite`:** O Planner recebe os `prerequisite_concepts` identificados pelo Critic (ex: `["Kundartiguador"]`), despacha Researchers apenas para esses conceitos, e agrega os novos `ResearcherOutput` ao estado existente (não substitui). O Writer então resintetiza com **todo** o contexto: resposta original + pré-requisitos descobertos. A resposta final começa explicando o pré-requisito e depois responde a pergunta original.

### Contrato de output do Summarizer (novo agente)

```python
# Summarizer — roda apenas após aprovação do Critic / Judge
SummarizerOutput = {
    "recap": str | None  # Resumo em bullet points gerado via Gemini 3.0 Flash Lite.
                         # Opcional (None) se a resposta principal for muito curta.
}
```

### Limites rígidos por agente (enforcement via grafo)

| Agente | Pode fazer | Não pode fazer |
|---|---|---|
| **Planner** | Classificar intent, decompor query, despachar Researchers, gerenciar checklist, HITL | Acessar Qdrant, escrever resposta |
| **Researcher** | Synonym expansion interna, busca Qdrant, re-ranking, retornar `ResearcherOutput` | Sintetizar ou escrever resposta |
| **Writer** | Sintetizar `researcher_outputs` em Markdown estruturado; reescrever com feedback do Critic (`poor_writing`) | Fazer busca, tomar decisão de qualidade |
| **Critic** | Avaliar qualidade; emitir `CriticOutput` com `rejection_type` | Fazer busca, reescrever resposta diretamente |
| **Summarizer** | Gerar um resumo (TL;DR) com Gemini 3.0 Flash Lite baseado apenas na saída do Writer | Acessar Qdrant, alterar o texto principal |
| **Judge** | Decisão final após `revision_count >= 2`: aprovar / nova pesquisa / fallback | Executar pesquisa diretamente |
| **DirectResponder** | Responder queries `"conversational"` diretamente com LLM | Acessar Qdrant |

### Decisão

> 🟢 **Decidido** — Topologia híbrida com 5 agentes + circuit breaker
>
> `revision_count` no estado global (máx. 3 tentativas). Judge ativo a partir da 2ª rejeição do Critic. Judge é membro permanente da topologia, não opcional.

---

## 4. Mecânicas do Researcher

> 🟢 **Decidido** — todas as subseções (4.1 a 4.4)

### 4.1 Query Transformation

> 🟢 **Decidido** — Synonym expansion + Query rewrite estruturado

**HyDE descartado** para este corpus: o Gemini Flash não conhece a terminologia técnica de Samael Aun Weor (ex: "Kundartiguador", "Átomo Anubis", "Tritocósmico"). HyDE geraria drift terminológico — recall enganoso para documentos próximos da alucinação, não da doutrina real.

**Estratégia adotada:**
1. A **query original** é sempre preservada e enviada como uma das sub-queries
2. **Synonym expansion via LLM**: variantes terminológicas adicionadas ao lado (não substituindo) a original
3. **Query rewrite estruturado**: reformulação com prompt calibrado ao vocabulário do corpus gnóstico
4. O Researcher **nunca substitui** a query original — apenas adiciona variantes concorrentes

### 4.2 Multi-Query RAG

> 🟢 **Decidido** — integrado ao mecanismo do Planner dinâmico

O Planner decompõe a query em sub-queries e as envia via `Send` API. Cada sub-query é processada por um Researcher independente. O número de sub-queries é dinâmico (decidido pelo Planner em runtime, com um teto máximo de 6 Researchers globais, ex: 4 iniciais + 2 pré-requisitos).

### 4.3 Metadata Filtering

> 🟢 **Decidido** — Pre-filters Diretos (Sem Fallback) (Decisão #16)

#### Dois tipos de filtro distintos

| Tipo | Campo | Fonte | Estratégia | Status |
|---|---|---|---|---|
| **Explícito** | `author`, `book`, `camara` | Aba de configuração do usuário na UI | Seguidos rigorosamente sempre que definidos na UI (o campo `camara` funciona como controle de acesso principal) | ✅ Decidido |
| **Semântico** | `author`, `book`, `camara` | `PlannerOutput.inferred_metadata` | Inferidos da query (ex: "apenas nos livros de Samael") e adicionados aos filtros de busca se possível | ✅ Decidido |

#### Fluxo interno do Researcher

```
sub_query + explict_filters + inferred_metadata
    │
    └─ Chamada Única: Qdrant search COM TODOS os pre-filters combinados
            │
            └─> ResearcherOutput
```

> **Nota:** Optou-se por não ter lógica de fallback (retentar caso < 5 chunks). Uma única chamada combina rigorosamente as configurações explícitas do usuário + inferência semântica. O filtro de `access` foi removido por ser redundante ao campo `camara`. O filtro `language` também foi descartado.

#### Estado de Saída do Researcher

```python
ResearcherOutput = {
    "sub_query": str,
    "retrieved_docs": list,
    "source_citations": list,
    "confidence_score": float,
}
```

#### Payload indexes obrigatórios (setup único — Fase 2.3)

```python
await client.create_payload_index("gnosis_books", "author",   PayloadSchemaType.KEYWORD)
await client.create_payload_index("gnosis_books", "book",     PayloadSchemaType.KEYWORD)
await client.create_payload_index("gnosis_books", "camara",   PayloadSchemaType.KEYWORD)
```

### 4.4 Cross-Encoder Re-Ranking

> 🟢 **Decidido** — **Vertex AI Ranking API**

Pipeline: bi-encoder retrieval (~30 docs do Qdrant) → Vertex AI Ranking API → top K (5-8 chunks) para o LLM.

**Justificativa:** Coerente com stack GCP/Gemini; sem cold start de container serverless; custo desprezível (~$0.00006/query para 30 docs); latência de rede mínima dentro da GCP.

| Opção | Decisão | Motivo |
|---|---|---|
| Vertex AI Ranking API ✅ | **Adotado** | GCP-native, serverless-friendly, custo irrisório |
| OSS cross-encoder | Descartado | Anti-padrão em Cloud Run (cold start + memória) |
| Cohere Rerank | Descartado | Vendor externo à GCP, sem vantagem de localidade |

---

## 5. Mecânicas do Planner

> 🟢 **Decidido**

### 5.1 Concurrent Researcher Dispatch

> 🟢 **Decidido** — LangGraph `Send` API com dispatch dinâmico

- Planner despacha Researchers em paralelo via `Send` API (não `asyncio.gather` manual)
- O número de Researchers é determinado em runtime pelo output do prompt de decomposição do Planner
- Cada `Send` encapsula uma sub-query + contexto de metadados inferidos da query

### 5.2 Execution Checklist

> 🟢 **Decidido** — lista de verificação embutida no `GraphState`

O `GraphState` global carrega um campo `execution_checklist: dict` que o Planner preenche na entrada e cada nó subsequente marca como concluído. A edge de saída de cada agente valida que o item correspondente no checklist está marcado antes de avançar.

```python
# Exemplo de checklist no estado:
execution_checklist = {
    "query_decomposed": False,
    "researchers_dispatched": False,
    "all_researchers_completed": False,
    "writer_completed": False,
    "critic_approved": False,
}
```

### 5.3 Human-in-the-Loop (HITL)

> 🟢 **Decidido** — Threshold estruturado integrado à decomposição (sem chamada LLM extra)

**Mecanismo:** O prompt do Planner combina três tarefas em uma única chamada LLM com output estruturado (JSON via Pydantic):
1. Classificar a clareza da query (score 1-5)
2. Decompor em sub-queries (se `clarity_score >= 3`)
3. Formular pergunta esclarecedora (se `clarity_score < 3`)

**Persistência para HITL:** LangGraph `interrupt_before` + checkpointer Supabase Postgres (já no stack). O grafo pausa, persiste estado, retorna a pergunta ao cliente mobile via webhook/SSE, e retoma quando a resposta chega.

```python
PlannerOutput = {
    "query_type": str,             # "conversational" | "knowledge_query"
    "clarity_score": int,          # 1-5 (só relevante se knowledge_query)
    "needs_clarification": bool,   # True se clarity_score < 3
    "clarification_question": str, # pergunta ao usuário (se needs_clarification)
    "sub_queries": list[str],      # sub-queries (se knowledge_query + sem clarificação)
    "inferred_metadata": dict,     # filtros de metadata detectados na query
    "checklist": dict              # execution checklist inicializado
}
```

> **Roteamento pelo `query_type`:** Se `"conversational"`, o grafo vai diretamente para um nó `DirectResponder` que responde sem acionar nenhum Researcher. Se `"knowledge_query"`, segue o pipeline RAG completo. Um único prompt do Planner cobre os dois casos — zero chamadas extras.

---

## 6. Gestão de Memória e Contexto

> 🟢 **Decidido** — Apenas Short-Term Memory (STM) para o MVP

Para garantir conversas fluidas sem explodir custos ou correr o risco de "memory drift", adotamos a seguinte estratégia:

### 6.1 Short-Term Memory (STM)
- **Checkpointer Nativo:** Utiliza o `checkpointer` do LangGraph persistido no Supabase Postgres (o mesmo já configurado para o HITL).
- **Janela Deslizante (Sliding Window):** Para evitar que o prompt fique demasiadamente grande, aplicamos truncamento no histórico do `GraphState`. Apenas as **últimas 10 mensagens** da conversa atual são injetadas no prompt do Planner.
- Isso permite resolver correferências e manter a fluidez da conversa de forma barata e altamente previsível.

### 6.2 Long-Term Memory (LTM)
- **Descartado para o MVP.** A criação de perfis relacionais ou uma base vetorial dedicada ao usuário (Agentic Memory) adicionaria complexidade arquitetural excessiva. O bot não reterá fatos do usuário entre sessões diferentes.

---

## 7. Observabilidade e Resiliência

> 🟢 **Decidido** — Strategic Minimum

### 6.1 Estratégia de Observabilidade — "Strategic Minimum"

> Filosofia adotada: **nem "Observe Everything" nem MVP cego**. Com multi-agente + múltiplas APIs de custo, os custos se compõem silenciosamente. Um loop Critic mal configurado pode gerar 9+ chamadas LLM por query sem aviso.

| Camada | Ferramenta | Fase | Justificativa |
|---|---|---|---|
| **Traces de grafo** | LangSmith (já ativo) | ✅ Agora | Debug de StateGraph multi-agente sem traces é inviável |
| **Cost meter por run** | LangSmith `on_llm_end` callback (~10 linhas) | ✅ Agora | Loops Critic + Vertex AI podem surpreender no custo |
| **Replay / Time-travel** | LangGraph checkpointer (Supabase Postgres) | ⏳ Fase 2 | Necessário para HITL de qualquer forma; replay vem de graça depois |
| **Métricas de negócio** | Dashboard customizado | ❌ Adiar | Over-engineering para MVP; decidir quando houver usuários reais |

> **Nota:** O checkpointer Supabase para HITL (Seção 5.3) e Replay compartilham a mesma infraestrutura — ao implementar HITL na Fase 2, Replay vem de graça sem custo extra de implementação.

### 6.2 Padrões de Resiliência a Falhas

> 🟢 **Decidido** — padrões adotados por nó

| Padrão | Aplicação | Fase |
|---|---|---|
| **Retry com backoff exponencial + Jitter** | Chamadas Gemini, Qdrant e Vertex AI Ranking (Jitter de 0~500ms para evitar thundering herd) | ✅ Fase 1 (junto com cada nó) |
| **Fallback de agente** | Researcher falha → busca simples sem re-rank | ✅ Fase 1 |
| **Circuit breaker** | APIs externas (Vertex AI, Gemini) com `tenacity` | ✅ Fase 1 |
| **Timeout por nó** | SLA de 30s por nó, configurável no `StateGraph` | ✅ Fase 1 |
| **Dead letter / Replay** | Via checkpointer Supabase (mesma infra do HITL) | ⏳ Fase 2 |

---

## 8. Log de Decisões Técnicas

> Registro cronológico das decisões tomadas durante o brainstorm.

| # | Data | Tópico | Decisão | Justificativa | Alternativas Descartadas |
|---|---|---|---|---|---|
| 1 | 18 Abr 2026 | Framework Agêntico | **LangGraph** | Já instalado, LangSmith wired, topologia Planner→Researchers paralelos é o core use case do framework | CrewAI (opaco para loops complexos), smolagents (não-determinístico para produção) |
| 2 | 18 Abr 2026 | Dinamismo do Planner | **Dinâmico em runtime (máx 6)** (Opção A) | Planner decide em runtime quantos Researchers despachar via `Send` API; máximo de 6 Researchers globais (ex: 4 iniciais + 2 pré-requisitos) | Topologia configurável fixa (Opção B), Híbrido MVP→dinâmico (Opção C) |
| 3 | 18 Abr 2026 | Terminação do loop Critic | **Híbrido: max-retries (3) + Judge** | `revision_count` no estado como guarda-chuva; Judge ativo na 2ª rejeição como circuit breaker inteligente | Max-retries simples sem Judge (sem inteligência no fallback) |
| 4 | 18 Abr 2026 | Papel do Judge | **Membro permanente da topologia** | Com Planner dinâmico, Judge é necessário para decisão inteligente no loop — não é opcional | Judge como árbitro de conflito Writer/Critic (papel mais restrito, descartado) |
| 5 | 18 Abr 2026 | Contrato do Researcher | **`ResearcherOutput` com `confidence_score`** | Critic precisa de sinal quantitativo além do texto; `source_citations` com metadados (autor, livro, câmara) habilitam o Writer a citar corretamente | Retorno somente de texto puro sem score (Critic cego) |
| 6 | 18 Abr 2026 | Query Transformation | **Synonym expansion + Query rewrite estruturado** | HyDE descartado: Gemini Flash não conhece terminologia doutrinária de Samael Aun Weor, geraria drift terminológico. Query original sempre preservada como sub-query âncora. | HyDE (risco de drift), Step-back prompting (generalização excessiva) |
| 7 | 18 Abr 2026 | Cross-Encoder Re-Ranking | **Vertex AI Ranking API** | GCP-native, serverless-friendly, latência mínima dentro da GCP, custo ~$0.00006/query (desprezível) | OSS cross-encoder (anti-padrão em Cloud Run), Cohere Rerank (vendor externo à GCP) |
| 8 | 18 Abr 2026 | HITL — Detecção de Ambiguidade | **Threshold estruturado integrado à decomposição** | Classificação de clareza (1-5) + decomposição em um único prompt Pydantic. Zero chamadas LLM extras. Checkpointer: Supabase Postgres (já no stack). | LLM dedicado como juiz de clareza (chamada extra por query, latência + custo desnecessários) |
| 9 | 18 Abr 2026 | Observabilidade — Filosofia | **"Strategic Minimum"** | Traces LangSmith (já ativo) + cost meter via `on_llm_end` callback (10 linhas). Replay adiado para Fase 2 junto com checkpointer HITL (mesma infra). Métricas de negócio: adiar. | "Observe Everything" (over-engineering para MVP), MVP cego (custo invisível com loop Critic) |
| 10 | 18 Abr 2026 | Resiliência — Padrões | **Retry (Backoff + Jitter) + Fallback + Circuit breaker + Timeout por nó** | Implementados na Fase 1 junto com cada nó. `tenacity` para retries com jitter (0~500ms) para evitar picos sincronizados de carga (thundering herd). Dead letter via checkpointer na Fase 2. | Resiliência sem padrão explícito (risco de falha silenciosa no pipeline) |
| 11 | 19 Abr 2026 | Responsabilidade da Synonym Expansion | **Interna ao Researcher** | O Planner decompõe em sub-queries de alto nível. Cada Researcher recebe UMA sub-query e internamente executa expansion + rewrite antes do Qdrant. Planner permanece agnóstico aos termos expandidos. | Expansion no Planner (acoplamento indevido; Planner precisaria conhecer o vocabulário do corpus) |
| 12 | 19 Abr 2026 | Roteamento de intent no Planner | **`query_type` no PlannerOutput** — `"conversational"` → DirectResponder (sem RAG) / `"knowledge_query"` → pipeline completo | Queries conversacionais ("olá, tudo bem?") não devem acionar Qdrant, Researchers ou Vertex AI. Economia de custo e latência, além de resposta mais natural. Zero chamadas extras — o Planner classifica o intent no mesmo prompt de decomposição. | Pipeline RAG para todas as queries (desperdício de custo e resposta robótica para conversas simples) |
| 13 | 19 Abr 2026 | Roteamento do Critic (`rejection_type`) | **`CriticOutput` com `rejection_type`: `"poor_writing"` → Writer / `"insufficient_content"` → Planner** | Evita disparar novo ciclo de pesquisa (Qdrant + Vertex AI) quando o problema é apenas qualidade de escrita. Critic envia `feedback` específico para o Writer reescrever — custo de uma chamada LLM, sem I/O externo. | Loop Critic sempre volta ao Planner independente do motivo (custo e latência desnecessários; RAG para problema de escrita é erro de design) |
| 14 | 19 Abr 2026 | Descoberta de pré-requisitos pelo Critic | **`rejection_type = "missing_prerequisite"` + campo `prerequisite_concepts: list[str]`** no `CriticOutput` | O Critic pode identificar que a resposta pressupõe conhecimento não pesquisado (ex: usuário perguntou Y, mas pré-requisito X não foi explicado). Planner despacha Researcher(s) APENAS para X; resultados de Y são preservados no estado via reducer. Writer resintetiza combinando ambos. O pré-requisito é surfaced proativamente sem nova pergunta ao usuário. | Ignorar pré-requisitos (resposta confusa para usuários); perguntar ao usuário sobre X (quebra o fluxo desnecessariamente — o Critic já identificou o gap) |
| 15 | 19 Abr 2026 | Formato de output do Writer | **Markdown adaptativo** com `WriterOutput { content, response_type, cited_sources }`. `response_type = "simple"` para queries de 1 Researcher (sem headers); `"structured"` para multi-tópico e pré-requisitos (seções `##` + rodapé de fontes) | Markdown sempre estruturado (headers até em respostas simples — UX de chat robótica); texto puro sem formatação (perde legibilidade em respostas longas e multi-tópico). Flutter precisa de `flutter_markdown` para renderização. |
| 16 | 19 Abr 2026 | Metadata Filtering | **Pre-filters Diretos (sem fallback)** — Tipos: Explícitos (UI, incluindo `camara` como segurança) e Semânticos (inferidos, ex: livros específicos). Uma chamada ao Qdrant com `author`, `book`, `camara`. Removidos `access` (redundante com `camara`), `language`, o loop de fallback (<5 chunks) e o `filter_applied` para evitar over-engineering. | Pre-filter com fallback (muita complexidade e heurística inconsistente para <5 chunks) |
| 17 | 20 Abr 2026 | Recap/Resumo da Resposta | **Agente Summarizer Dedicado (Gemini 3.0 Flash Lite)** | Adição de um nó `Summarizer` pós-Critic (Opção C). O Writer foca 100% na profundidade do texto Markdown principal (usando Flash padrão). O Summarizer roda ao final, gerando um `recap` isolado usando um modelo mais leve e barato. | Incorporar `recap` no output JSON do Writer (risco comprovado de queda na qualidade e profundidade do texto principal devido à carga cognitiva e geração de múltiplos blocos de texto grandes). |
| 18 | 20 Abr 2026 | Arquitetura de Memória | **STM (Janela 10 msgs) / Sem LTM** | STM via checkpointer nativo do LangGraph com truncamento limitando o histórico a 10 mensagens para não inflar o prompt. LTM descartado no MVP para reduzir complexidade e riscos de alucinação/privacidade. | LTM via Agentic RAG; LTM via perfil relacional do usuário. |

---

## 9. Próximos Passos

> 🟢 **Definido** — roadmap de implementação pós-brainstorm

### Fase 1 — Foundations (implementar antes de qualquer agente)

| # | Tarefa | Detalhe |
|---|---|---|
| 1.1 | **Definir `GraphState` completo** | `TypedDict` com todos os campos: `chat_history: list`, `original_query`, `sub_queries`, `researcher_outputs: Annotated[list, operator.add]`, `writer_output`, `critic_feedback`, `revision_count`, `execution_checklist`, `hitl_clarification` |
| 1.2 | **Instrumentar cost meter** | `on_llm_end` callback no LangSmith — ~10 linhas, feito antes de qualquer nó |
| 1.3 | **Configurar `tenacity`** | Retry (com backoff exponencial e jitter de 0~500ms) + circuit breaker para Gemini, Qdrant e Vertex AI |

### Fase 2 — Researcher MVP

| # | Tarefa | Detalhe |
|---|---|---|
| 2.1 | **Researcher single-query** | Synonym expansion + query rewrite → Qdrant (~30 docs) → Vertex AI Ranking API → top-8 → retorna `ResearcherOutput` |
| 2.2 | **Testar isoladamente** | Unit tests no Researcher antes de conectar ao Planner |
| 2.3 | **Metadata Filtering** | Implementar pre-filters (Decisão #16): criar payload indexes (`author`, `book`, `camara`) e injetar parâmetros (UI + Semânticos) na busca do Qdrant. |

### Fase 3 — Planner + HITL

| # | Tarefa | Detalhe |
|---|---|---|
| 3.1 | **Prompt do Planner** | Output Pydantic: `clarity_score`, `needs_clarification`, `sub_queries`, `inferred_metadata`, `checklist` |
| 3.2 | **Send API fan-out** | Planner despacha N Researchers via `Send` dinamicamente |
| 3.3 | **HITL + Checkpointer** | `interrupt_before` + Supabase Postgres checkpointer; integração com endpoint FastAPI para retomar execução |

### Fase 4 — Writer + Critic + Judge

| # | Tarefa | Detalhe |
|---|---|---|
| 4.1 | **Writer** | Sintetiza `researcher_outputs` + `source_citations` em resposta estruturada |
| 4.2 | **Critic** | Avalia `confidence_score` + qualidade textual; incrementa `revision_count` |
| 4.3 | **Judge** | Ativado quando `revision_count >= 2`; decide: aprovar / nova pesquisa / fallback |
| 4.4 | **Summarizer** | Executado após aprovação final do Critic/Judge; gera `recap` (TL;DR) com Gemini 3.0 Flash Lite |
| 4.5 | **Loop completo** | Conectar todas as edges condicionais; testar cenários de rejeição e resumo |

### Fase 5 — Observabilidade Fase 2 + QA

| # | Tarefa | Detalhe |
|---|---|---|
| 5.1 | **Replay via checkpointer** | Já disponível após Fase 3.3 — ativar e documentar |
| 5.2 | **Metadata Filtering refinado** | Avaliar impacto no recall pós-implementação |
| 5.3 | **Evaluation suite** | Avaliar qualidade do RAG com dataset de perguntas gnósticas (ver notebook existente) |

---

_Documento vivo — atualizado a cada sessão de brainstorm. Brainstorm inicial concluído em 18 Abr 2026 com 10 decisões técnicas registradas._
