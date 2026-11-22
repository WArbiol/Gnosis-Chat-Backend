# 🏛️ Gnosis Chat — Backend API (Agentic RAG)

> Production-grade **Agentic RAG (Retrieval-Augmented Generation)** API built with **FastAPI** and orchestrated via **LangGraph**, powering the study assistant at [Gnosis Chat](https://gnosischat.com).

The system handles complex philosophical and conceptual inquiries across a closed corpus of 90+ esoteric works and PDFs with strict source traceability, inline academic citations `[Title, p. X]`, and high-throughput streaming via Server-Sent Events (SSE).

---

## 📑 Table of Contents

- [Overview & Why Agentic RAG?](#-overview--why-agentic-rag)
- [Software Architecture (Clean Architecture)](#-software-architecture-clean-architecture)
- [Agentic Graph Topology (LangGraph)](#-agentic-graph-topology-langgraph)
- [Production Engineering & Model Resilience](#-production-engineering--model-resilience)
- [Ingestion Pipeline & Contextual Retrieval](#-ingestion-pipeline--contextual-retrieval)
- [Tech Stack](#-tech-stack)
- [Quick Start](#-quick-start)
- [Environment Configuration (.env)](#-environment-configuration-env)
- [Key API Endpoints](#-key-api-endpoints)
- [Testing & Diagnostics](#-testing--diagnostics)
- [Production Deployment (Google Cloud Run)](#-production-deployment-google-cloud-run)

---

## 🎯 Overview & Why Agentic RAG?

The standard Naive RAG approach (*naive text chunking ➔ embeddings ➔ Top-K retrieval ➔ monolithic LLM generation*) struggles significantly on dense, domain-specific literary corpuses due to three core challenges:
1. **Semantic Ambiguity:** Identical esoteric terms carry nuanced meanings across different authors, books, and chronological periods.
2. **Citation Hallucinations:** Without rigorous cross-verification, monolithic models frequently invent chapters or non-existent page numbers.
3. **Cost and Latency Bottlenecks:** Injecting unranked, raw document chunks into expensive models on every turn increases operational costs and degrades Time to First Token (TTFT).

**Gnosis Chat Backend** solves this by decoupling procedural logic into specialized **LangGraph** nodes, utilizing dynamic multi-query decomposition, Cross-Encoder Re-Ranking on Google Vertex AI, and autonomous reflection loops before delegating synthesis to the writer.

---

## 📐 Software Architecture (Clean Architecture)

The backend strictly follows **Clean Architecture** principles, ensuring core business logic and agent orchestrations remain fully isolated from HTTP frameworks, database vendors, and external AI SDKs:

```
app/
├── domain/                  # Layer 1: Core business logic, entities, and domain exceptions
│   └── exceptions.py        # Framework-agnostic exceptions (e.g., QuotaExceededException)
├── application/             # Layer 2: Use Cases and abstract Ports / Gateways
│   ├── interfaces/          # Abstract contracts (LLMGateway, VectorStoreGateway, RerankerGateway)
│   └── use_cases/           # Application use cases (AskRagUseCase, ClarifyUseCase)
├── infrastructure/          # Layer 3: Concrete external adapters & drivers
│   ├── google/              # Google GenAI SDK (Gemini) & Vertex AI Ranking API
│   ├── qdrant/              # Vector database adapter (Qdrant Cloud & Local)
│   ├── supabase/            # PostgreSQL checkpointer, user authentication, and storage
│   └── langgraph/           # State persistence and checkpointer implementations
├── api/                     # Layer 4: Presenters & HTTP controllers (FastAPI)
│   └── v1/                  # REST & SSE routers (chat, conversations, citations, payments, auth)
└── agents/                  # LangGraph state machine, state schemas, and specialized agent nodes
```

> **The Dependency Rule:** Dependencies strictly point inward. The domain and use case layers have zero knowledge of FastAPI, Supabase, or external APIs, enabling instantaneous unit testing with mocks and frictionless infrastructure swaps.

---

## 🤖 Agentic Graph Topology (LangGraph)

Query lifecycles are coordinated by a deterministic state machine built on **LangGraph**:

```mermaid
flowchart TD
    Start([Incoming User Query]) --> Orch[Orchestrator<br/><i>Gemini 3.5 Flash Lite</i>]
    
    Orch -->|Conceptual Question / RAG| Res[Researcher<br/><i>Qdrant + Vertex AI Ranking</i>]
    Orch -->|Chit-chat / Greetings| Direct[Direct Response<br/><i>Gemini 3.5 Flash Lite</i>]
    Orch -->|Ambiguous / Clarification| AskUser[Ask User<br/><i>Human-in-the-Loop</i>]
    
    Res --> Crit[Critique<br/><i>Gemini 3.5 Flash Lite</i>]
    
    Crit -->|Insufficient / Refine sub-queries| Res
    Crit -->|Sufficient or Retry Limit Reached| Writer[Writer<br/><i>Gemini 3.8 Flash (Streaming)</i>]
    
    Direct --> End([End / SSE Stream])
    AskUser --> End
    Writer --> End
```

### Specialist Node Responsibilities

| Agent / Node | Model / Service | Responsibility |
|---|---|---|
| **`orchestrator`** | Gemini 3.5 Flash Lite | Entry point (executes once). Classifies user intent, extracts metadata constraints (`books`, `authors`, `chamber_levels`), and decomposes the inquiry into up to 3 focused sub-queries. |
| **`researcher`** | Qdrant + Vertex AI Ranking API | Executes filtered dense vector retrieval and applies Cross-Encoder Re-Ranking with adaptive depth (Top 10 on first search, Top 15 on first retry, Top 20 on second retry). |
| **`critique`** | Gemini 3.5 Flash Lite | Evaluates evidence sufficiency as a senior domain expert. If context is incomplete, extracts author-authentic terminology, reformulates sub-queries or broadens page windows, and routes **directly** back to the Researcher (max 2 retries). |
| **`writer`** | Gemini 3.8 Flash | Streams the final synthesis in real-time via SSE. Adheres to strict academic tone, traceable citations `[Book, p. X]`, a summary tag (`---RECAP---`), and 3 exploratory follow-up questions (`---SUGESTOES---`). |
| **`direct_response`** | Gemini 3.5 Flash Lite | Handles general greetings, chit-chat, and assistant meta-questions without incurring RAG overhead. |
| **`ask_user`** | Gemini 3.5 Flash Lite | Pauses the graph (Human-in-the-Loop) to request user clarification when queries are too vague to yield faithful results. |

---

## ⚡ Production Engineering & Model Resilience

Designed for 99.9% availability and low-latency interaction under heavy workloads:

### 1. Eliminating the "Typewriter Effect" in Streaming
Models featuring hybrid/chain-of-thought reasoning modes often pause for 1.2s–1.6s between streamed output chunks to deliberate. For user-facing text generation (`writer`), we deploy high-throughput streaming models (`gemini-3.8-flash`), delivering over 1,700 characters/second continuously.

### 2. Automatic Multi-Tier Fallback Cascade
To withstand transient cloud provider outages (`503 UNAVAILABLE`) or temporary rate limiting (`429`), requests automatically cascade across fallback tiers without terminating the user's connection:
- **Tier 1 (Primary):** `gemini-3.8-flash` — Premier theological depth and fluid streaming.
- **Tier 2 (Fast Fallback):** `gemini-3.5-flash` — High-availability secondary model.
- **Tier 3 (High-Availability Safe Guard):** `gemini-2.5-flash` — Reliable fallback to guarantee response delivery.

### 3. Balanced Round-Robin Sub-Query Aggregation
When multi-query decomposition produces diverse candidate sets, the chunks re-ranked by Vertex AI are merged using a **balanced Round-Robin algorithm**, ensuring all angles of a composite question are equally represented in the context window.

---

## 📚 Ingestion Pipeline & Contextual Retrieval

Data quality is enforced during preprocessing (`scripts/process_pdfs.py` and `scripts/ingest.py`):

1. **Document Cleaning:** Document parsing via `unstructured` and `pypdf`, stripping digital artifacts, footers, headers, and noise.
2. **Generous Semantic Windows:** Slicing at `max_chars = 2000` with `overlap_chars = 300..400` ensures philosophical arguments are not split mid-thought.
3. **Contextual Retrieval (Structured Prefixes):** Every chunk is prepended with explicit metadata before embedding:
   ```text
   [Work: The Perfect Matrimony | Author: Samael Aun Weor | Chamber: 1 | Chapter: The Sacred Fire | Page: 45]
   <complete paragraph text...>
   ```
4. **Vector Embeddings & Indexing:** Dense vectors generated via `gemini-embedding-2-preview` and upserted into Qdrant Cloud (`gnosis_books` collection) with persistent progress tracking (`data/ingest_checkpoint.json`).

---

## 🛠️ Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| **Runtime & Package Manager** | Python 3.12 + `uv` | Modern Python runtime with strict typing and fast dependency management |
| **Web Framework** | FastAPI 0.115+ / Uvicorn | Asynchronous web framework with Pydantic v2 and Server-Sent Events (SSE) |
| **Agent Orchestration** | LangGraph 0.2+ | Stateful multi-agent graph with checkpoints and Human-in-the-Loop workflows |
| **Vector Database** | Qdrant Cloud / Local | Dense vector storage with payload metadata filtering |
| **Re-Ranking** | Vertex AI Ranking API | Cloud-native Cross-Encoder for high-precision semantic re-ranking |
| **Language Models** | Google Gemini (3.8 Flash, 3.5 Flash Lite) | Task-specialized LLMs via official `google-genai` SDK |
| **Embeddings** | `gemini-embedding-2-preview` | Multilingual semantic embedding model |
| **Auth & Relational Store** | Supabase (PostgreSQL, RLS, Storage) | JWT authentication, chat session persistence, and PDF signed URLs |
| **Payments & Billing** | Stripe API | Subscription management, tiered usage quotas, and webhooks |
| **Deployment Platform** | Google Cloud Run & Docker | Serverless container hosting with Application Default Credentials (ADC) |

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.12**
- [`uv`](https://github.com/astral-sh/uv) package manager (recommended)
- Docker (optional, for running local Qdrant)
- Google Cloud SDK (`gcloud`) installed

### 1. Clone & Install Dependencies

```bash
cd gnosis-chat-backend

# Sync dependencies and configure virtual environment
uv sync
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
```

### 3. Local Google Cloud Authentication (ADC)

To authenticate with **Vertex AI Ranking API** and Gemini without using long-lived private key `.json` files:

```bash
gcloud auth application-default login
```

### 4. Run the Development Server

> [!CAUTION]
> **DO NOT USE UVLOOP:** The `google-genai` SDK relies on internal gRPC/threading loops that can deadlock under `uvloop` on Linux environments. Uvicorn must be run using Python's default `asyncio` loop policy.

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Access the interactive API documentation:
- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🔐 Environment Configuration (.env)

| Variable | Description | Example |
|---|---|---|
| `GOOGLE_API_KEY` | Google AI Studio API Key for Gemini models | `AIzaSy...` |
| `GOOGLE_CLOUD_PROJECT` | GCP Project ID (required for Vertex AI Ranking API) | `gnosis-chat-prod` |
| `QDRANT_CLOUD_URL` | Qdrant Cloud cluster endpoint | `https://xyz.qdrant.tech:6333` |
| `QDRANT_API_KEY` | Qdrant Cloud authentication key | `...` |
| `SUPABASE_URL` | Supabase instance URL | `https://xyz.supabase.co` |
| `SUPABASE_ANON_KEY` | Supabase anonymous public key | `sb_publishable_...` |
| `SUPABASE_SERVICE_ROLE_KEY`| Supabase backend service role secret (never expose to client) | `sb_secret_...` |
| `STRIPE_SECRET_KEY` | Stripe Secret API Key | `sk_test_...` / `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signature secret | `whsec_...` |
| `APP_ENV` | Application environment (`development`, `production`) | `development` |

---

## 📡 Key API Endpoints

All active endpoints are grouped under the `/api/v1` prefix:

### Chat & Agentic Intelligence
- `POST /api/v1/chat/ask` — Initiates an Agentic RAG request via **Server-Sent Events (SSE)**.
  - `status` event: Real-time agent transitions (`orchestrator`, `researcher`, `critique`).
  - `token` event: Live token-by-token stream from the `writer`.
  - `final` event: Complete structured response, bibliographic citations, and recap.
- `POST /api/v1/chat/clarify` — Resumes a paused Human-in-the-Loop session (`ask_user`) with user clarification.

### Conversations & Citations
- `GET /api/v1/conversations/` — Retrieves active conversations for the authenticated user.
- `GET /api/v1/conversations/{id}` — Returns conversation metadata and historical messages.
- `GET /api/v1/citations/{id}` — Fetches verified citation metadata and original source page.
- `GET /api/v1/pdfs/{filename}/signed-url` — Generates a secure, temporary signed URL to view source PDFs.

### Payments & Webhooks
- `POST /api/v1/payments/create-checkout-session` — Generates a Stripe checkout session.
- `POST /api/v1/payments/webhook` — Consumes Stripe subscription lifecycle events and updates quota tiers.

---

## 🧪 Testing & Diagnostics

### Automated Test Suite
Unit tests mock out external LLM and vector gateways, allowing the complete graph topology to be verified offline:

```bash
# Run unit and integration tests
uv run pytest
```

### Direct Graph & Endpoint Diagnostics
Quickly test graph flow or API endpoints without launching the full web server:

```bash
# Isolated end-to-end LangGraph state test
uv run scratch/test_full_graph.py

# SSE streaming endpoint test
uv run scratch/test_api_endpoint.py
```

### Static Analysis & Linting
```bash
# Type check with Mypy
uv run mypy app

# Lint with Ruff
uv run ruff check app
```

---

## ☁️ Production Deployment (Google Cloud Run)

The application is containerized and hosted serverlessly on **Google Cloud Run**.

### 1. Service Account IAM Permissions
In production, Cloud Run authenticates with Vertex AI using the attached Google Service Account:
- Grant the **Discovery Engine Viewer** role (`roles/discoveryengine.viewer`) to the service account (`gnosis-chat-backend-sa`).

### 2. Deploy via Google Cloud CLI

```bash
gcloud run deploy gnosis-chat-api \
  --source . \
  --service-account="gnosis-chat-backend-sa@YOUR_GCP_PROJECT.iam.gserviceaccount.com" \
  --set-env-vars GOOGLE_CLOUD_PROJECT="YOUR_GCP_PROJECT",QDRANT_CLOUD_URL="https://your-cluster.qdrant.io",APP_ENV="production" \
  --allow-unauthenticated \
  --region us-central1
```

---

## 📄 License

Proprietary. All rights reserved by [Gnosis Chat](https://gnosischat.com).
