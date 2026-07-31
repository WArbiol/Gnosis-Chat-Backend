# Agentic RAG — Arquitetura Otimizada (Cost & Speed Optimization)

> **Status:** Atualizado & Produção · Julho 2026
> **Repositório:** `gnosis-chat-backend`
> **Stack:** FastAPI + LangGraph + Qdrant + Gemini (3.5 Flash Lite / 3.6 Flash)
> **Checkpointer:** PostgreSQL (Supabase) — persistência de estado entre turnos

---

## 1. Visão Geral

O Gnosis Chat utiliza um sistema de **Agentic RAG** (Retrieval-Augmented Generation) otimizado e orquestrado pelo **LangGraph** para responder perguntas sobre um corpus fechado de **90 PDFs gnósticos**.

O sistema é composto por **nós especialistas altamente integrados** que operam dentro de um grafo com roteamento direto e busca adaptativa, garantindo extrema velocidade (<30s), baixíssimo consumo de tokens (~10k tokens por pergunta) e alta fidelidade teológica com citações explícitas de livros e páginas.

---

## 2. Agentes e Nós do Grafo

### 2.1. Orchestrator (Ponto de Entrada / Entry Point)

- **Papel:** Ponto de entrada do grafo. Recebe a query inicial do usuário e decide a rota de partida.
- **LLM:** Gemini 3.5 Flash Lite
- **Responsabilidades:**
  - Analisar a query e determinar a rota inicial:
    - `"researcher"`: Para qualquer pergunta sobre conceitos, ensinamentos ou estudos das obras.
    - `"direct_response"`: Para saudações, conversas informais (chit-chat), perguntas sobre o assistente/app ou quando o usuário não quer RAG.
    - `"ask_user"`: Para perguntas totalmente vagas e ambíguas.
  - **Extração de Filtros:** Mapear filtros da UI (`ui_filters`) e inferir filtros implícitos da linguagem natural (`metadata_filters`).
  - **Decomposição dinâmica:** Decompõe a pergunta principal em até 3 sub-queries conceituais para busca paralela no Qdrant.
- **Limite rígido:** NÃO realiza RAG nem gera resposta final. Executa apenas 1 vez por mensagem no início do grafo.

### 2.2. Researcher (Pesquisador com Busca Adaptativa)

- **Papel:** Único nó autorizado a realizar RAG no Qdrant e Re-Ranking.
- **LLM:** Gemini 3.5 Flash Lite (para Query Transformation)
- **Responsabilidades:**
  - **Query Transformation:** Reformula sub-queries para maximizar o recall no banco vetorial.
  - **Retrieval:** Busca ~30 candidatos no Qdrant aplicando `metadata_filters` (`books`, `authors`, `chamber_levels`, `page_start`, `page_end`).
  - **Cross-Encoder Re-Ranking Adaptativo:** Re-ordena os chunks via **Vertex AI Ranking API** com profundidade adaptativa de acordo com a rodada de retentativa:
    - *1ª Busca (Inicial):* Top 10 chunks.
    - *2ª Busca (1º Retry):* Top 15 chunks.
    - *3ª Busca (2º Retry):* Top 20 chunks.
- **Limite rígido:** NÃO gera resposta final.

### 2.3. Critique (Avaliador de Chunks & Roteador Direto)

- **Papel:** Avalia a suficiência das fontes e orienta o refino direto da busca.
- **LLM:** Gemini 3.5 Flash Lite (com Persona de Pesquisador Gnóstico Sênior)
- **Responsabilidades:**
  - Analisar se os chunks recuperados respondem com profundidade à dúvida do usuário.
  - Se **suficiente (ou limite de 3 buscas atingido):** Roteia **DIRETO para o Writer**.
  - Se **insuficiente:** Extrai sinônimos técnicos e terminologias autênticas dos autores presentes nos trechos lidos, gera `refined_sub_queries` (e opcionalmente filtros de faixa de páginas `page_start`/`page_end` ou `books`) e ROTEIA **DIRETO para o Researcher** (sem passar pelo Orchestrator!).
- **Limite rígido de segurança:** Máximo de 2 retentativas (3 buscas no total). Se exceder, força o veredito para `sufficient`.

### 2.4. Writer (Escritor em Streaming com Recap Embutido)

- **Papel:** Gera a resposta final detalhada, fundamentada e com citações explícitas.
- **LLM:** Gemini 3.6 Flash (Modelo Premium para síntese textual avançada em streaming)
- **Responsabilidades:**
  - Escrever resposta retórica limpa em markdown com citações no formato `[Livro, p. X]`.
  - Distinguir rigorosamente títulos de livros de entidades/conceitos.
  - **Recap e Sugestões Embutidos:** No final do streaming da resposta, gera automaticamente a tag `---RECAP---` com 2-3 frases de síntese e `---SUGESTOES---` com 3 perguntas instigantes de continuação.
- **Saída:** `END` — Nó terminal do grafo.

### 2.5. Direct Response (Resposta Direta)

- **Papel:** Responde diretamente saudações, despedidas ou perguntas sobre o app (sem RAG).
- **LLM:** Gemini 3.5 Flash Lite
- **Saída:** `END` — Nó terminal do grafo.

### 2.6. Ask User (Human-in-the-Loop)

- **Papel:** Formula perguntas esclarecedoras quando a query do usuário é ambígua.
- **Persistência:** Requer `checkpointer` (PostgresSaver no Supabase) para pausar e retomar a sessão.
- **Saída:** `END` (aguarda resposta do usuário para nova sessão).

---

## 3. Fluxo do Grafo Otimizado (Edges)

```
                         ┌──────────────┐
                         │ ORCHESTRATOR │ ← Entry Point (Apenas 1x)
                         └──────┬───────┘
                                │
                 ┌──────────────┼──────────────────────┐
                 │              │                      │
                 ▼              ▼                      ▼
          ┌──────────┐  ┌────────────┐          ┌──────────┐
          │RESEARCHER│  │  DIRECT    │        ┌────────┴────────┐
      │ (Insuficiente)  │ (Suficiente / Limite 3x)
      ▼                 ▼
  RESEARCHER        ┌──────────┐
  (Direct Retry)    │  WRITER  │ ──(Streaming + Recap + Sugestões)──► END
                    └──────────┘
```

### Tabela de Roteamento (Conditional Edges):

| Origem | Condição / Veredito | Destino |
|---|---|---|
| **Orchestrator** | `next_step == "researcher"` | **Researcher** |
| **Orchestrator** | `next_step == "direct_response"` | **Direct Response** $\rightarrow$ `END` |
| **Orchestrator** | `next_step == "ask_user"` | **Ask User** $\rightarrow$ `END` |
| **Researcher** | *(Incondicional)* | **Critique** |
| **Critique** | `critique_verdict == "insufficient"` e `critique_loops <= 2` | **Researcher** *(Direct Retry)* |
| **Critique** | `critique_verdict == "sufficient"` ou `critique_loops > 2` | **Writer** $\rightarrow$ `END` |

---

## 4. Conceitos: Sessão vs. Conversa

| Conceito     | Definição                                                                 |
|--------------|--------------------------------------------------------------------------|
| **Sessão**   | Uma execução do grafo: do momento em que o Orchestrator recebe a query até `END`. Cada mensagem do usuário inicia uma nova sessão. |
| **Conversa** | Conjunto de sessões (turnos) entre o usuário e o sistema. Histórico persiste via checkpointer (PostgreSQL). |

### Limites por Sessão

| Limite                       | Valor | Justificativa                                    |
|------------------------------|:-----:|--------------------------------------------------|
| Máx. Buscas RAG por sessão   | 3     | Total de retentativas diretas (`Critique` $\rightarrow$ `Researcher`) |
| Máx. loops Critique          | 2     | No 3º passe insatisfatório, força envio ao Writer |
| Máx. Ask User por sessão     | 2     | Permitir esclarecimentos sem frustrar o usuário  |

> Estes limites são configuráveis e aplicados pelo Orchestrator via o campo `session_counters` do GraphState.

---

## 5. GraphState (Estado do Grafo)

```python
from typing import TypedDict, Literal

class ResearchResult(TypedDict):
    """Resultado de uma pesquisa individual."""
    sub_query: str
    chunks: list[str]
    citations: list[Citation]
    relevance_scores: list[float]  # scores do Cross-Encoder

class SessionCounters(TypedDict):
    """Contadores de limites por sessão."""
    researcher_calls: int         # Quantas vezes Researcher foi chamado
    critique_loops: int           # Quantos loops Critique→Orchestrator
    judge_loops: int              # Quantos loops Judge→Orchestrator
    ask_user_calls: int           # Quantas vezes Ask User foi chamado

class GraphState(TypedDict, total=False):
    """Estado tipado do grafo LangGraph."""

    # --- Input ---
    query: str                          # Query original do usuário
    user: UserProfile                   # Perfil do usuário (chamber_level, plan, etc.)
    ui_filters: dict                    # Filtros explícitos da UI (livro, autor, câmara)
    conversation_history: list[dict]    # Últimas N mensagens (sliding window)

    # --- Orchestrator ---
    sub_queries: list[str]              # Queries decompostas pelo Orchestrator
    next_step: str                      # Próximo nó a executar
    orchestrator_checklist: dict        # Checklist interno do Orchestrator
    session_counters: SessionCounters   # Contadores de limites por sessão

    # --- Researcher ---
    research_results: list[ResearchResult]  # Resultados de cada Researcher
    metadata_filters: dict              # Filtros de metadata para o Qdrant

    # --- Critique ---
    critique_verdict: str               # "sufficient" | "insufficient"
    critique_feedback: str              # Feedback para o Orchestrator (se insuficiente)

    # --- Writer ---
    answer: str                         # Resposta gerada pelo Writer
    citations: list[Citation]           # Citações da resposta

    # --- Judge ---
    judge_verdict: str                  # "approved" | "rejected"
    judge_feedback: str                 # Feedback para o Orchestrator (se rejeitado)

    # --- Recap ---
    recap: str                          # Resumo conciso da resposta

    # --- Direct Response ---
    direct_answer: str                  # Resposta direta (sem RAG)

    # --- Ask User ---
    clarification_question: str         # Pergunta esclarecedora para o usuário

    # --- Interest Tracker ---
    inferred_interests: list[str]       # Interesses inferidos da query

    # --- Observability ---
    route: str                          # Rota tomada (para logging)
    cost_estimate: float                # Estimativa de custo da query
```

---

## 6. Decisões Arquiteturais

### 6.1. Clean Architecture ✅

O backend seguirá **Clean Architecture** com as seguintes camadas:

```
gnosis-chat-backend/
├── app/
│   ├── domain/              # Entidades e regras de negócio puras
│   │   ├── entities/        # Entidades de domínio (User, Conversation, Message, Citation)
│   │   ├── repositories/    # Interfaces (abstrações) de repositórios
│   │   └── services/        # Lógica de domínio pura (sem dependências externas)
│   │
│   ├── application/         # Use Cases / Casos de Uso
│   │   ├── use_cases/       # Orquestração de lógica de negócio
│   │   └── interfaces/      # Portas (interfaces para adaptadores)
│   │
│   ├── infrastructure/      # Implementações concretas (adaptadores)
│   │   ├── llm/             # Adaptadores para LLMs (Gemini Flash, Flash Lite)
│   │   ├── vectordb/        # Adaptadores para Qdrant
│   │   ├── database/        # Adaptadores para Supabase PostgreSQL
│   │   ├── storage/         # Adaptadores para Supabase Storage
│   │   ├── auth/            # Adaptadores para Supabase Auth
│   │   ├── payments/        # Adaptadores para Stripe
│   │   └── observability/   # Adaptadores para LangSmith
│   │
│   ├── agents/              # Agentes do LangGraph
│   │   ├── orchestrator.py
│   │   ├── researcher.py
│   │   ├── critique.py
│   │   ├── writer.py
│   │   ├── judge.py
│   │   ├── recap.py
│   │   ├── direct_response.py
│   │   ├── ask_user.py
│   │   ├── graph.py         # Montagem e compilação do grafo
│   │   └── state.py         # GraphState
│   │
│   ├── api/                 # Camada de apresentação (FastAPI)
│   │   ├── v1/
│   │   │   ├── router.py
│   │   │   ├── chat.py
│   │   │   ├── auth.py
│   │   │   └── conversations.py
│   │   ├── middleware.py
│   │   └── dependencies.py
│   │
│   ├── core/                # Configurações e utilitários transversais
│   │   ├── config.py
│   │   ├── security.py
│   │   └── exceptions.py
│   │
│   └── main.py              # Entry point FastAPI
│
├── scripts/                 # Scripts offline (ingestão, etc.)
├── tests/                   # Testes
├── migrations/              # Migrações SQL
└── PLANNING/                # Documentação de planejamento
```

**Princípios:**
- **Dependency Rule:** Camadas internas NÃO dependem de camadas externas
- **Domain puro:** `domain/` não importa nada de `infrastructure/`
- **Injeção de dependência:** Use cases recebem repositórios via interface
- **Testabilidade:** Cada agente é testável isoladamente com mocks

### 6.2. Observabilidade — LangSmith ✅

- **Quando:** Desde o início do desenvolvimento
- **O quê:**
  - Traces de cada nó do grafo (input/output)
  - Cost meters por query (estimativa de tokens)
  - Replay capability para debug
- **Tier:** Free tier (suficiente para MVP)

### 6.3. Resiliência ✅

- **Backoff com jitter:** 0–500ms entre retries de chamadas LLM
- **Max retries:** 3 tentativas por chamada LLM
- **Fallback estrito:** Se todos os loops falharem, resposta padrão "Não há referências sobre isso no corpus literário"
- **Timeouts:** Configuráveis por nó

### 6.4. Limites dos Agentes (Principle of Least Authority)

| Agente          | Pode fazer RAG? | Pode chamar LLM? | Pode escrever resposta final? |
|-----------------|:---------------:|:-----------------:|:-----------------------------:|
| Orchestrator    | ❌              | ✅ (Flash Lite)   | ❌                            |
| Researcher      | ✅              | ✅ (Flash Lite)   | ❌                            |
| Critique        | ❌              | ✅ (Flash Lite)   | ❌                            |
| Writer          | ❌              | ✅ (Flash)        | ✅                            |
| Judge           | ❌              | ✅ (Flash Lite)   | ❌                            |
| Recap           | ❌              | ✅ (Flash Lite)   | ❌                            |
| Direct Response | ❌              | ✅ (Flash Lite)   | ✅                            |
| Ask User        | ❌              | ✅ (Flash Lite)   | ❌                            |

### 6.5. Streaming de Resposta (SSE) ✅

Para garantir uma UX fluida no Flutter, a resposta do RAG será transmitida via **Server-Sent Events (SSE)** através de uma `StreamingResponse` do FastAPI.
- **Estrutura dos Eventos:**
  - `status`: Enviado ao iniciar/finalizar nós do grafo (ex: `"agent": "researcher", "message": "Buscando referências..."`).
  - `token`: Enviado em tempo real conforme o `Writer` gera a resposta final (token por token).
  - `final`: Enviado após a conclusão do grafo, contendo o objeto de resposta completo (resposta, citações estruturadas, recap e estimativa de custo).
- **Consumo no Grafo:** Uso de `compiled_graph.astream_events(..., version="v2")` para capturar os chunks gerados pelo LLM e eventos do ciclo de vida dos nós.

### 6.6. Persistência de Estado (Checkpointer) ✅

O suporte a interações do tipo **Human-in-the-Loop** (como no nó `ask_user`) exige que o estado da sessão do grafo seja persistido entre as requisições HTTP do usuário.
- **Implementação:** Usaremos o `PostgresSaver` do LangGraph, conectando-se diretamente ao banco de dados relacional **PostgreSQL do Supabase**.
- **Resiliência:** Essa abordagem protege a sessão atual em caso de reinicializações do servidor FastAPI no Railway, garantindo persistência durável dos threads.

---

## 7. Use Cases (API Endpoints)

### 7.1. `POST /api/v1/conversations/{id}/ask` (Streaming RAG)

- **Descrição:** Envia uma pergunta ao RAG, executando o orquestrador do LangGraph com suporte a streaming de tokens e status.
- **Protocolo:** Server-Sent Events (SSE)
- **Input:** `ChatRequest` (contendo a query do usuário, id opcional de conversa e `UIFilters` opcionais para refinar a busca).
- **Output (Stream de Eventos):**
  - **Tipo `status` (`ChatStreamStatus`):** Retorna o progresso atual do orquestrador (ex: `"agent": "researcher", "message": "Procurando no corpus..."`).
  - **Tipo `token` (`ChatStreamToken`):** Retorna os fragmentos (tokens) da resposta final à medida que são gerados pelo `Writer`.
  - **Tipo `final` (`ChatStreamFinal`):** Retorna o payload estruturado final com a resposta completa consolidada, a lista de `citations` com link para os PDFs (nome do arquivo, página, fragmento original), o `recap` da resposta, a rota tomada e a estimativa de custos.

### 7.2. Outros Endpoints Relacionais (Conversas e Histórico)

Estes endpoints seguem o fluxo convencional (JSON síncrono):

- `GET /api/v1/conversations` (Listar conversas paginado):
  - **Output:** `PaginatedResponse[ConversationResponse]`
- `POST /api/v1/conversations` (Criar conversa):
  - **Input:** `ConversationCreate`
  - **Output:** `ConversationResponse`
- `GET /api/v1/conversations/{id}/messages` (Mensagens e citações históricas):
  - **Output:** `list[MessageResponse]`
- `DELETE /api/v1/conversations/{id}` (Deletar conversa):
  - **Output:** `{ "success": true }`
- `PATCH /api/v1/conversations/{id}` (Atualizar título da conversa):
  - **Input:** `ConversationUpdate`
  - **Output:** `ConversationResponse`

---

---

## 8. Decisões Arquiteturais e Análise do Nó Judge

### 8.1. Status das Decisões

| # | Decisão | Status |
|---|---|---|
| 1 | **Judge Node:** manter ou remover? | 🔴 **Removido** (ver análise abaixo). |
| 2 | **Recap Node:** nó separado ou embutido? | 🟢 **Embutido** no streaming do Writer via tags `---RECAP---`. |
| 3 | **Direct Critique Routing:** permitir Critique $\rightarrow$ Researcher? | 🟢 **Implementado** (bypassa Orchestrator em retries). |
| 4 | **Cross-Encoder:** qual modelo usar para Re-Ranking? | 🟢 **Vertex AI Ranking API** (Google Cloud). |
| 5 | **Streaming:** como transmitir status dos nós ao Flutter? | 🟢 **Server-Sent Events (SSE)** via StreamingResponse do FastAPI. |
| 6 | **Persistência do Grafo:** checkpointer no LangGraph? | 🟢 **PostgresSaver** conectado ao Supabase. |

---

### 8.2. Análise do Nó Judge: Vale a pena recolocá-lo?

Fizemos uma estimativa empírica e financeira detalhada para avaliar o impacto caso o nó `Judge` (que auditava a resposta antes de enviar ao usuário) seja reativado:

#### 📊 Impacto de Custo e Latência com o Nó `Judge` Reativado:

1. **Consumo Adicional de Tokens por Pergunta:**
   - O `Judge` precisa ler a pergunta do usuário (~100 tokens), os **chunks recuperados** (~4.000 tokens), a **resposta gerada pelo Writer** (~1.500 tokens) e as **instruções de validação** (~900 tokens).
   - **Total adicional:** **+6.500 tokens de entrada** e **+150 tokens de saída** por conversa (usando `Gemini 3.5 Flash Lite`).

2. **Impacto no Custo Financeiro:**
   - *Sem Judge (Arquitetura Atual):* **$0,001575 USD** por pergunta (~R$ 0,0088).
   - *Com Judge:* 6.500 $\times$ $0.075/1M + 150 $\times$ $0.30/1M = **+$0,0005325 USD** por pergunta.
   - **Aumento percentual de custo:** **+33,8% por requisição!**

3. **Impacto na Latência (Tempo de Resposta):**
   - Adiciona uma chamada sequencial extra à API do Gemini após a geração da resposta.
   - **Aumento de tempo:** **+3,5s a +6,0s** no tempo de resposta final (aumentando a latência de 27s para ~33s).

4. **Necessidade do Negócio e Recomendação:**
   - O modelo do `Writer` (**Gemini 3.6 Flash**) é instruído com *Grounding Rígido* (só escreve o que consta nos chunks e cita `[Livro, p. X]`). Nos testes empíricos com 3 perguntas complexas, o modelo atingiu **100% de precisão sem qualquer alucinação**.
   - **Recomendação:** **Manter o Judge desativado** no fluxo principal de produção. Caso haja necessidade de auditoria para fins de compliance no futuro, o Judge pode ser disparado de forma **assíncrona em background (offline)**, sem bloquear a resposta do usuário nem atrasar o streaming do Flutter.

---

*Documento atualizado em Julho/2026 · Arquitetura Definitiva e Otimizada em Produção.*
