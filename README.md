# 🏛️ Gnosis Chat — Backend API (Agentic RAG)

> API de **RAG Agêntico (Retrieval-Augmented Generation)** de alta precisão desenvolvida em **FastAPI** e orquestrada com **LangGraph**, alimentando o assistente de estudos do [Gnosis Chat](https://gnosischat.com).

O sistema responde dúvidas conceituais e filosóficas complexas sobre um acervo fechado de obras e PDFs gnósticos com rastreabilidade rigorosa de fontes, citações bibliográficas estritas `[Obra, pág. X]` e streaming de alta vazão via Server-Sent Events (SSE).

---

## 📑 Sumário

- [Visão Geral & Por Que Agentic RAG?](#-visão-geral--por-que-agentic-rag)
- [Arquitetura de Software (Clean Architecture)](#-arquitetura-de-software-clean-architecture)
- [Topologia do Grafo Agêntico (LangGraph)](#-topologia-do-grafo-agêntico-langgraph)
- [Resiliência em Produção & Cascata de Modelos](#-resiliência-em-produção--cascata-de-modelos)
- [Pipeline de Ingestão & Contextual Retrieval](#-pipeline-de-ingestão--contextual-retrieval)
- [Stack Tecnológica](#-stack-tecnológica)
- [Início Rápido (Getting Started)](#-início-rápido-getting-started)
- [Configuração de Ambiente (.env)](#-configuração-de-ambiente-env)
- [Rotas Principais da API](#-rotas-principais-da-api)
- [Testes e Diagnósticos](#-testes-e-diagnósticos)
- [Deploy em Produção (Google Cloud Run)](#-deploy-em-produção-google-cloud-run)

---

## 🎯 Visão Geral & Por Que Agentic RAG?

O fluxo tradicional de RAG (*chunking simples ➔ embedding ➔ Top-K ➔ LLM monolítica*) falha gravemente em acervos literários densos por três motivos principais:
1. **Ambiguidade Semântica:** Termos idênticos assumem significados divergentes dependendo do autor, do contexto histórico e do livro em que aparecem.
2. **Alucinação de Fontes:** Sem validação cruzada, modelos monolíticos tendem a inventar capítulos ou números de páginas.
3. **Custo e Latência:** Injetar blocos brutos em modelos pesados a cada interação encarece a operação e degrada o *Time to First Token* (TTFT).

O **Gnosis Chat Backend** resolve esse problema desacoplando as decisões lógicas em nós especialistas do **LangGraph**, aplicando decomposição dinâmica de perguntas, Cross-Encoder Re-Ranking na Google Vertex AI e ciclos autônomos de reflexão/crítica antes da redação final.

---

## 📐 Arquitetura de Software (Clean Architecture)

O backend segue estritamente a **Clean Architecture** (Arquitetura Limpa), garantindo que as regras de negócio e a inteligência do grafo independam de frameworks HTTP, provedores de vetores ou bancos de dados:

```
app/
├── domain/                  # Camada 1: Lógica de negócio, entidades e exceções fundamentais
│   └── exceptions.py        # Exceções puras (ex: QuotaExceededException)
├── application/             # Camada 2: Use Cases e Portas/Interfaces abstratas
│   ├── interfaces/          # Gateways abstratos (LLMGateway, VectorStoreGateway, RerankerGateway)
│   └── use_cases/           # Casos de uso da aplicação (AskRagUseCase, ClarifyUseCase)
├── infrastructure/          # Camada 3: Adaptadores concretos externos
│   ├── google/              # SDK Gemini (google-genai) e Vertex AI Ranking API
│   ├── qdrant/              # Adaptador vetorial Qdrant Cloud / Local
│   ├── supabase/            # Autenticação, banco relacional e armazenamento
│   └── langgraph/           # Checkpointers persistentes de estado
├── api/                     # Camada 4: Apresentadores e rotas FastAPI (REST + SSE)
│   └── v1/                  # Endpoints v1 (chat, conversations, citations, payments, auth)
└── agents/                  # LangGraph: State, nós especialistas e arestas do grafo
```

> **Regra Fundamental de Dependência:** As dependências apontam sempre para o interior. O núcleo do domínio e dos casos de uso desconhece se o transporte é HTTP, CLI ou WebSocket, viabilizando testes unitários rápidos com mocks e substituição transparente de infraestrutura.

---

## 🤖 Topologia do Grafo Agêntico (LangGraph)

O fluxo de processamento de cada pergunta é coordenado por uma máquina de estados finita do **LangGraph**:

```mermaid
flowchart TD
    Start([Entrada da Mensagem]) --> Orch[Orchestrator<br/><i>Gemini 3.5 Flash Lite</i>]
    
    Orch -->|Pergunta Conceitual / RAG| Res[Researcher<br/><i>Qdrant + Vertex AI Ranking</i>]
    Orch -->|Chit-chat / Saudações| Direct[Direct Response<br/><i>Gemini 3.5 Flash Lite</i>]
    Orch -->|Pergunta Ambígua / HIL| AskUser[Ask User<br/><i>Human-in-the-Loop</i>]
    
    Res --> Crit[Critique<br/><i>Gemini 3.5 Flash Lite</i>]
    
    Crit -->|Insuficiente / Refina sub-queries| Res
    Crit -->|Suficiente ou Limite de Retries| Writer[Writer<br/><i>Gemini 3.8 Flash (Streaming)</i>]
    
    Direct --> End([Fim / Stream SSE])
    AskUser --> End
    Writer --> End
```

### Papel de Cada Especialista

| Agente / Nó | Modelo / Serviço | Responsabilidade |
|---|---|---|
| **`orchestrator`** | Gemini 3.5 Flash Lite | Ponto de entrada (executado apenas 1x). Classifica a intenção, extrai filtros de metadados (`books`, `authors`, `chamber_levels`) e decompõe a pergunta em até 3 sub-queries conceituais. |
| **`researcher`** | Qdrant + Vertex AI Ranking API | Executa busca vetorial densa com filtragem e aplica Cross-Encoder Re-Ranking via Vertex AI com profundidade adaptativa (Top 10 na 1ª busca, Top 15 no 1º retry, Top 20 no 2º retry). |
| **`critique`** | Gemini 3.5 Flash Lite | Atua como pesquisador sênior auditando as evidências. Se insuficientes, extrai terminologias das próprias obras, reformula sub-queries ou expande páginas e envia **direto** ao Researcher (máximo de 2 iterações). |
| **`writer`** | Gemini 3.8 Flash | Redige a resposta final fundamentada via streaming SSE, aplicando formatação acadêmica, citações rastreáveis `[Livro, pág. X]`, resumo (`---RECAP---`) e 3 perguntas instigantes (`---SUGESTOES---`). |
| **`direct_response`** | Gemini 3.5 Flash Lite | Responde com cordialidade a saudações, dúvidas sobre o assistente ou mensagens que dispensam RAG. |
| **`ask_user`** | Gemini 3.5 Flash Lite | Pausa o grafo (Human-in-the-Loop) e solicita esclarecimentos ao usuário quando a consulta for indeterminada. |

---

## ⚡ Resiliência em Produção & Cascata de Modelos

Para garantir alta disponibilidade (99.9%) e streaming contínuo sem lentidão ao usuário, o backend adota estratégias de resiliência corporativa:

### 1. Eliminação do "Efeito Máquina de Escrever"
Modelos que operam com modos híbridos de raciocínio sofrem de latência interna entre blocos de saída (1.2s a 1.6s por chunk). Para o nó `writer`, priorizamos modelos otimizados para alta vazão contínua (`gemini-3.8-flash`), atingindo mais de 1.700 caracteres por segundo sem engasgos de interface.

### 2. Cascata Multi-Tier Automática
Em picos de tráfego, limites de cota (`429`) ou instabilidade de provedor (`503 UNAVAILABLE`), a chamada chave migra instantaneamente de degrau sem derrubar a conexão do cliente:
- **Tier 1 (Principal):** `gemini-3.8-flash` — Máxima fidelidade de citações e fluidez retórica.
- **Tier 2 (Fallback Estável):** `gemini-3.5-flash` — Alternativa de alta performance comprovada.
- **Tier 3 (Alta Disponibilidade):** `gemini-2.5-flash` — Camada consolidada de segurança para entrega garantida.

### 3. Agregação Round-Robin de Sub-queries
Quando o orquestrador gera múltiplas sub-queries paralelas, os chunks reordenados pela Vertex AI são intercalados em formato **Round-Robin balanceado**, garantindo que todas as nuances da dúvida do usuário sejam representadas no contexto do redator.

---

## 📚 Pipeline de Ingestão & Contextual Retrieval

A alta fidelidade das respostas decorre de um pipeline rigoroso de preparação de dados (`scripts/process_pdfs.py` e `scripts/ingest.py`):

1. **Extração Limpa:** Uso de `unstructured` e `pypdf` com eliminação de cabeçalhos, rodapés e ruídos de digitalização.
2. **Janela Semântica Ampla:** Fatiamento em `max_chars = 2000` com `overlap_chars = 300..400` para preservar argumentos teológicos inteiros.
3. **Contextual Retrieval (Prefixo Estruturado):** Cada chunk recebe metadados estruturados antes do cálculo do embedding:
   ```text
   [Obra: O Matrimônio Perfeito | Autor: Samael Aun Weor | Câmara: 1 | Cap: O Fogo Sagrado | Pág: 45]
   <conteúdo do fragmento do livro...>
   ```
4. **Vetorização e Indexação:** Vetores gerados pelo modelo `gemini-embedding-2-preview` e persistidos na coleção `gnosis_books` do **Qdrant** com checkpointing de recuperação (`data/ingest_checkpoint.json`).

---

## 🛠️ Stack Tecnológica

| Componente | Tecnologia | Finalidade |
|---|---|---|
| **Linguagem & Runtime** | Python 3.12 + `uv` | Ambiente moderno com tipagem estrita e resolução rápida de pacotes |
| **Framework Web** | FastAPI 0.115+ / Uvicorn | Servidor assíncrono com validação Pydantic e suporte a SSE |
| **Orquestração de Agentes** | LangGraph 0.2+ | Grafo de estados com checkpoints e suporte a Human-in-the-Loop |
| **Banco Vetorial** | Qdrant (Cloud / Local) | Armazenamento de embeddings densos com filtragem por metadados |
| **Re-Ranking** | Vertex AI Ranking API | Cross-Encoder de alta precisão do Google Cloud |
| **Modelos de Linguagem** | Google Gemini (3.8 Flash, 3.5 Flash Lite) | Modelos especializados por nó via SDK `google-genai` |
| **Embeddings** | `gemini-embedding-2-preview` | Geração de vetores semânticos com 768/1536 dimensões |
| **Auth & Banco de Dados** | Supabase (PostgreSQL, RLS, Storage) | Autenticação JWT, histórico de conversas e signed URLs para PDFs |
| **Pagamentos & Assinaturas**| Stripe API | Gestão de planos de assinatura e webhooks de cota |
| **Hospedagem & Infra** | Google Cloud Run & Docker | Infraestrutura serverless com Application Default Credentials (ADC) |

---

## 🚀 Início Rápido (Getting Started)

### Pré-requisitos
- **Python 3.12**
- Gerenciador de pacotes [`uv`](https://github.com/astral-sh/uv) (recomendado)
- Docker (opcional, para rodar Qdrant localmente)
- Google Cloud SDK (`gcloud`) configurado

### 1. Clonar e Instalar Dependências

```bash
cd gnosis-chat-backend

# Criação do ambiente virtual e instalação com uv
uv sync
```

### 2. Configurar Variáveis de Ambiente

Copie o arquivo de exemplo e preencha suas chaves:

```bash
cp .env.example .env
```

### 3. Autenticação Local do Google Cloud (ADC)

Para utilizar a **Vertex AI Ranking API** e os modelos Gemini sem necessidade de arquivos de credenciais `.json`:

```bash
gcloud auth application-default login
```

### 4. Executar o Servidor

> [!CAUTION]
> **NÃO USE UVLOOP:** O SDK `google-genai` utiliza mecanismos de threading/gRPC incompatíveis com `uvloop` no Linux, podendo causar deadlocks silenciosos. Sempre execute o Uvicorn sob o event loop nativo `asyncio`.

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Acesse a documentação interativa da API no navegador:
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- Redoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🔐 Configuração de Ambiente (.env)

| Variável | Descrição | Exemplo |
|---|---|---|
| `GOOGLE_API_KEY` | Chave de API do Google AI Studio para acesso ao Gemini | `AIzaSy...` |
| `GOOGLE_CLOUD_PROJECT` | ID do projeto no Google Cloud (para Vertex AI Ranking API) | `gnosis-chat-prod` |
| `QDRANT_CLOUD_URL` | Endpoint do cluster Qdrant Cloud | `https://xyz.qdrant.tech:6333` |
| `QDRANT_API_KEY` | Chave de autenticação do Qdrant Cloud | `...` |
| `SUPABASE_URL` | URL da instância Supabase | `https://xyz.supabase.co` |
| `SUPABASE_ANON_KEY` | Chave pública anônima do Supabase | `sb_publishable_...` |
| `SUPABASE_SERVICE_ROLE_KEY`| Chave privada do backend (nunca expor no frontend) | `sb_secret_...` |
| `STRIPE_SECRET_KEY` | Chave secreta de API da Stripe | `sk_test_...` / `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | Chave de verificação de assinatura de webhooks da Stripe | `whsec_...` |
| `APP_ENV` | Ambiente de execução (`development`, `production`) | `development` |

---

## 📡 Rotas Principais da API

Todas as rotas da versão atual estão sob o prefixo `/api/v1`:

### Chat & Inteligência Agêntica
- `POST /api/v1/chat/ask` — Envia pergunta para processamento RAG agêntico via **Server-Sent Events (SSE)**.
  - Evento `status`: Atualizações em tempo real do agente ativo (`orchestrator`, `researcher`, `critique`).
  - Evento `token`: Streaming de texto gerado em tempo real pelo `writer`.
  - Evento `final`: Payload consolidado com resposta completa, fontes citadas e recap.
- `POST /api/v1/chat/clarify` — Retoma uma sessão pausada em Human-in-the-Loop (`ask_user`) fornecendo a clarificação solicitada.

### Conversas & Citações
- `GET /api/v1/conversations/` — Lista conversas do usuário autenticado.
- `GET /api/v1/conversations/{id}` — Detalhes e mensagens de uma conversa específica.
- `GET /api/v1/citations/{id}` — Retorna dados detalhados e página original de uma citação.
- `GET /api/v1/pdfs/{filename}/signed-url` — Gera URL assinada temporária para visualização do PDF no Supabase Storage.

### Assinaturas & Webhooks
- `POST /api/v1/payments/create-checkout-session` — Cria sessão de checkout Stripe.
- `POST /api/v1/payments/webhook` — Recebe eventos de pagamento e atualiza limites de cota.

---

## 🧪 Testes e Diagnósticos

### Suíte de Testes Automatizados
O projeto inclui testes unitários que utilizam mocks para os gateways de LLM e vetores, permitindo validar o grafo sem chamadas externas:

```bash
# Executa todos os testes unitários e de integração
uv run pytest
```

### Scripts de Diagnóstico Rápido
Para validar o grafo ou o endpoint de streaming diretamente pelo terminal:

```bash
# Teste completo do grafo LangGraph (isolado, sem subir HTTP)
uv run scratch/test_full_graph.py

# Teste do endpoint de streaming SSE
uv run scratch/test_api_endpoint.py
```

### Verificação Estática e Linting
```bash
# Verificação de tipos com Mypy
uv run mypy app

# Linting e formatação com Ruff
uv run ruff check app
```

---

## ☁️ Deploy em Produção (Google Cloud Run)

O backend é conteinerizado e implantado de forma serverless no **Google Cloud Run**.

### 1. Permissões IAM da Conta de Serviço
Em produção, a aplicação autentica na Vertex AI via conta de serviço nativa do Cloud Run (sem arquivos `.json` de chaves):
- Atribua o papel **Discovery Engine Viewer** (`roles/discoveryengine.viewer`) à Conta de Serviço do Cloud Run (`gnosis-chat-backend-sa`).

### 2. Deploy via Google Cloud CLI

```bash
gcloud run deploy gnosis-chat-api \
  --source . \
  --service-account="gnosis-chat-backend-sa@SEU_PROJETO_GCP.iam.gserviceaccount.com" \
  --set-env-vars GOOGLE_CLOUD_PROJECT="SEU_PROJETO_GCP",QDRANT_CLOUD_URL="https://seu-cluster.qdrant.io",APP_ENV="production" \
  --allow-unauthenticated \
  --region us-central1
```

---

## 📄 Licença

Proprietário. Todos os direitos reservados por [Gnosis Chat](https://gnosischat.com).
