# Agentic RAG — Arquitetura Definitiva

> **Status:** Em definição · Sessão de alinhamento 2026-06-30
> **Repositório:** `gnosis-chat-backend`
> **Stack:** FastAPI + LangGraph + Qdrant + Gemini (Flash Lite / Flash)
> **Checkpointer:** PostgreSQL (Supabase) — persistência de estado entre turnos

---

## 1. Visão Geral

O Gnosis Chat utiliza um sistema de **Agentic RAG** (Retrieval-Augmented Generation) orquestrado pelo **LangGraph** para responder perguntas sobre um corpus fechado de **90 PDFs gnósticos**.

O sistema é composto por **múltiplos agentes especializados** que operam dentro de um grafo com loops de auto-correção, garantindo qualidade e precisão nas respostas.

---

## 2. Agentes (Nós do Grafo)

### 2.1. Orchestrator (Nó Central / Entry Point)

- **Papel:** Orquestrador central do grafo. Recebe a query do usuário e **sempre decide o próximo passo**. Todas as rotas passam por ele.
- **LLM:** Gemini 3.0 Flash Lite
- **Responsabilidades:**
  - Analisar a query e determinar a rota (`researcher`, `writer`, `recap`, `direct_response`, `ask_user`, `END`).
  - **Extração e Resolução de Filtros:** Mapear e estruturar os filtros da consulta:
    - *Filtros Explícitos:* Receber os filtros vindos da UI (`ui_filters` contendo `books`, `authors`, `chamber_levels`, `chapters`).
    - *Filtros Implícitos:* Analisar a query em linguagem natural e inferir intenções de filtragem (ex: "segundo o livro A Grande Rebelião..." ➔ `books=["A Grande Rebelião"]`).
    - *Filtros Autônomos:* Ter autonomia para injetar novos filtros ou restringir a pesquisa proativamente (ex: forçar a busca apenas no livro deduzido, mesmo que o usuário não tenha selecionado nenhum filtro na UI), salvando-os em `metadata_filters`.
  - **Decomposição dinâmica:** Para queries simples, envia 1 query ao Researcher. Para queries complexas, decompõe em sub-queries e dispara **N Researchers em paralelo** (máx. 6 por sessão).
  - Manter um **checklist interno** para garantir que todas as etapas foram cumpridas.
  - Após receber resultados do Critique, decidir: avançar para Writer, pedir mais pesquisas, ou ir para Ask User se algo não ficou claro.
  - Após receber feedback do Judge, decidir: avançar para Recap (se aprovado) ou pedir reescrita ao Writer (se rejeitado).
- **Limite rígido:** NÃO faz RAG. NÃO escreve resposta final.
- **Fluxo resumido:** O Orchestrator é revisitado após CADA etapa (Critique → Orchestrator, Judge → Orchestrator, Ask User → Orchestrator) e sempre toma a próxima decisão.

### 2.2. Researcher (Pesquisador)

- **Papel:** Único agente autorizado a realizar RAG no Qdrant.
- **LLM:** Gemini 3.0 Flash Lite (para Query Transformation)
- **Responsabilidades:**
  - **Query Transformation:** Reformula a query para melhorar recall (sinônimos, expansão), sem distorcer a intenção do usuário.
  - **Metadata Filtering:** Consome os filtros salvos em `metadata_filters` (`books`, `authors`, `chamber_levels`, `chapters`) e constrói a query booleana exata do Qdrant usando os metadados equivalentes.
  - **Retrieval:** Busca ~30 chunks no Qdrant (gnosis_books + opcionalmente user_interests).
  - **Cross-Encoder Re-Ranking:** Filtra os top ~10 chunks mais relevantes via **Vertex AI Ranking API** (Google Cloud).
- **Limite rígido:** NÃO gera resposta final. NÃO avalia qualidade.
- **Concorrência:** Pode haver múltiplos Researchers em paralelo quando o Orchestrator decompõe a query em sub-queries (máx. 6 concorrentes, conforme decisão anterior).

### 2.3. Critique (Avaliador de Chunks)

- **Papel:** Avalia se os chunks recuperados pelo Researcher são suficientes para responder a pergunta.
- **LLM:** Gemini 3.0 Flash Lite
- **Responsabilidades:**
  - Verificar se os chunks cobrem a pergunta
  - Se **suficiente:** Reportar ao Orchestrator que pode avançar para o Writer
  - Se **insuficiente:** Reportar ao Orchestrator com sugestões (reformular query, ajustar filtros, alterar top-K)
- **Loop:** `Researcher → Critique → Orchestrator` (máx. 2 loops de retry)
- **Limite rígido:** NÃO faz RAG. NÃO escreve resposta.

### 2.4. Writer (Escritor)

- **Papel:** Gera a resposta final baseada nos chunks aprovados pelo Critique.
- **LLM:** Gemini 3.0 Flash (modelo mais capaz para síntese textual)
- **Responsabilidades:**
  - Escrever resposta retórica e fundamentada nos chunks
  - Incluir citações (pdf_name, page, snippet)
  - Fallback estrito: se chunks insuficientes, responder "Não há referências sobre isso no corpus literário"
- **Limite rígido:** NÃO faz RAG. Usa APENAS os chunks fornecidos.

### 2.5. Judge (Verificador de Diretrizes) ✅ Obrigatório

- **Papel:** Verificação rápida da resposta do Writer contra diretrizes de qualidade.
- **LLM:** Gemini 3.0 Flash Lite (prompt enxuto, checagem leve)
- **Responsabilidades:**
  - Verificar se a resposta NÃO alucina (não inventa informações fora dos chunks)
  - Verificar se as citações estão corretas
  - Verificar se não mistura informações de fontes diferentes de forma ambígua
  - Se **aprovado:** Reportar ao Orchestrator que pode avançar para Recap
  - Se **reprovado:** Reportar ao Orchestrator com feedback para reescrita
- **Loop:** `Writer → Judge → Orchestrator` (máx. 1 retry)
- **Limite rígido:** NÃO reescreve. Apenas avalia.

### 2.6. Recap (Sumarizador)

- **Papel:** Gera um resumo/recap conciso da resposta aprovada.
- **LLM:** Gemini 3.0 Flash Lite
- **Responsabilidades:**
  - Gerar um recap de 2-3 frases da resposta final
  - Esse recap pode ser usado no Flutter para preview de mensagem
- **Saída:** `END` — Nó terminal do grafo.

### 2.7. Direct Response (Resposta Direta)

- **Papel:** Responde diretamente queries que NÃO precisam de RAG.
- **LLM:** Gemini 3.0 Flash Lite
- **Exemplos:** Saudações, perguntas sobre o app, queries fora do escopo
- **Saída:** `END` — Nó terminal do grafo.

### 2.8. Ask User (Human-in-the-Loop) ✅ MVP

> **Nota arquitetural:** Esta decisão **sobrescreve** o ADR-B5 do SSOT original que dizia "LangGraph sem checkpointer". O `ask_user` requer persistência de estado do grafo entre turnos de conversa, portanto o LangGraph **usará checkpointer** (PostgreSQL/Supabase).

- **Papel:** Quando o Orchestrator identifica ambiguidade na query, faz uma pergunta esclarecedora ao usuário.
- **Responsabilidades:**
  - Formular pergunta clara e concisa
  - Pausar o grafo e aguardar resposta do usuário
  - Retomar o grafo com a resposta do usuário como contexto adicional
- **Implicação arquitetural:** Requer `checkpointer` (LangGraph) para persistir o estado do grafo entre turnos de conversa.

---

## 3. Fluxo do Grafo (Edges)

```
                         ┌──────────────┐
                         │ ORCHESTRATOR │ ← Entry Point
                         │  (Central)   │
                         └──────┬───────┘
                                │
                 ┌──────────────┼──────────────────────┐
                 │              │              │        │
                 ▼              ▼              ▼        ▼
          ┌──────────┐  ┌────────────┐  ┌────────┐  ┌──────────┐
          │RESEARCHER│  │  DIRECT    │  │ASK USER│  │  RECAP   │
          │(1..N)    │  │ RESPONSE   │  │(HIL)   │  │(terminal)│
          └────┬─────┘  └─────┬──────┘  └────┬───┘  └────┬─────┘
               │              │              │            │
               ▼              ▼              ▼            ▼
          ┌──────────┐      END         ORCHESTRATOR     END
          │ CRITIQUE │       
          └────┬─────┘
               │
               ▼
         ORCHESTRATOR ──► WRITER
                           │
                           ▼
                      ┌──────────┐
                      │  JUDGE   │
                      └────┬─────┘
                           │
                           ▼
                      ORCHESTRATOR ──► RECAP ──────► END
```

### Conditional Edges (do Orchestrator):

| Condição (`next_step`) | Destino          |
|------------------------|------------------|
| `"researcher"`         | Researcher       |
| `"writer"`             | Writer           |
| `"recap"`              | Recap            |
| `"direct_response"`    | Direct Response  |
| `"ask_user"`           | Ask User (HIL)   |
| `"END"`                | END              |

### Fixed Edges:

| Origem          | Destino  |
|-----------------|----------|
| Researcher      | Critique |
| Critique        | Orchestrator |
| Writer          | Judge    |
| Judge           | Orchestrator |
| Recap           | END      |
| Direct Response | END      |

---

## 4. Conceitos: Sessão vs. Conversa

| Conceito     | Definição                                                                 |
|--------------|--------------------------------------------------------------------------|
| **Sessão**   | Uma execução do grafo: do momento em que o Orchestrator recebe a query até `END`. Cada mensagem do usuário inicia uma nova sessão. |
| **Conversa** | Conjunto de sessões (turnos) entre o usuário e o sistema. Histórico persiste via checkpointer (PostgreSQL). |

### Limites por Sessão

| Limite                       | Valor | Justificativa                                    |
|------------------------------|:-----:|--------------------------------------------------|
| Máx. Researchers por sessão  | 7     | Total de chamadas ao Researcher (incluindo retries após Critique) |
| Máx. loops Critique→Orchestrator | 2 | Evitar loops infinitos de re-pesquisa            |
| Máx. loops Judge→Orchestrator | 1     | Evitar loops infinitos de reescrita              |
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

## 8. Decisões Pendentes

| # | Decisão | Status |
|---|---|---|
| 1 | Judge: obrigatório ou condicional? | ✅ Obrigatório (leve, Flash Lite) |
| 2 | Ask User (HIL): MVP ou fase futura? | ✅ MVP (requer checkpointer LangGraph) |
| 3 | Cross-Encoder: qual modelo usar para Re-Ranking? | ✅ Vertex AI Ranking API (Google Cloud) |
| 4 | Streaming: como transmitir status dos nós ao Flutter? | ✅ Server-Sent Events (SSE) via StreamingResponse do FastAPI |
| 5 | Use Cases detalhados com schemas Pydantic | ✅ Resolvido: definidos no `app/schemas/chat.py` |
| 6 | Revisar ADR-B5: LangGraph agora COM checkpointer (PostgreSQL) | ✅ Resolvido: PostgresSaver conectado ao Supabase |

---

*Documento finalizado em 2026-06-30 · Sessão de alinhamento do Agentic RAG*
*Próxima etapa: Implementação do Grafo do LangGraph (nós e edges) no `app/agents/`*
