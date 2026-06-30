# Casos de Uso (Use Cases) — Gnosis Chat Backend

> **Status:** Esboço para Alinhamento · 2026-06-30
> **Objetivo:** Definir as interações esperadas entre o frontend (Flutter), o usuário, o banco de dados e os serviços de IA.
> 
> ⚠️ **Nota de Eficiência:** Os casos de uso de CRUD de conversas/mensagens (UC03 a UC07) e autenticação são gerenciados **diretamente pelo Flutter via SDK do Supabase** (com segurança garantida pelas regras de Row-Level Security - RLS). O backend FastAPI fica responsável única e exclusivamente pela inteligência (RAG), HIL, ingestão e controle de cotas.

---

## 1. Mapeamento Geral de Use Cases

| ID | Nome do Caso de Uso | Ator Principal | Executado Por | Rota / Mecanismo |
|---|---|---|---|---|
| **UC01** | Enviar Pergunta ao Chat (Ask RAG) | Usuário (Mobile) | **FastAPI Backend** | `POST /api/v1/conversations/{id}/ask` (SSE) |
| **UC02** | Responder a Esclarecimento (Human-in-the-Loop) | Usuário (Mobile) | **FastAPI Backend** | `POST /api/v1/conversations/{id}/clarify` (SSE) |
| **UC03** | Listar Conversas Ativas | Usuário (Mobile) | *Flutter ➔ Supabase SDK* | Conexão Direta (PostgreSQL via RLS) |
| **UC04** | Visualizar Histórico de Conversa | Usuário (Mobile) | *Flutter ➔ Supabase SDK* | Conexão Direta (PostgreSQL via RLS) |
| **UC05** | Criar Nova Conversa | Usuário (Mobile) | *Flutter ➔ Supabase SDK* | Conexão Direta (PostgreSQL via RLS) |
| **UC06** | Renomear Conversa | Usuário (Mobile) | *Flutter ➔ Supabase SDK* | Conexão Direta (PostgreSQL via RLS) |
| **UC07** | Deletar Conversa | Usuário (Mobile) | *Flutter ➔ Supabase SDK* | Conexão Direta (PostgreSQL via RLS) |
| **UC08** | Ingestão e Processamento de PDFs | Administrador | **Script Backend** | Execução Offline (`scripts/ingest.py`) |
| **UC09** | Controle de Limites e Assinatura | Sistema | **FastAPI Backend** | Middleware / Verificação antes do RAG |

---

## 2. Detalhamento dos Casos de Uso do Backend (Espaço para Preenchimento)

### UC01: Enviar Pergunta ao Chat (Ask RAG)
* **Objetivo:** Processar uma nova pergunta através do orquestrador de múltiplos agentes e retornar a resposta e status em tempo real.
* **Pré-condições:** Usuário autenticado, conexão com a internet ativa, limite de mensagens do plano não atingido.

```
[ Espaço em Branco — A completar com o fluxo principal de sucesso e fluxos secundários ]
```

---

### UC02: Responder a Esclarecimento (Human-in-the-Loop)
* **Objetivo:** Retomar o processamento do grafo que foi pausado pelo nó `ask_user` após o usuário fornecer a informação solicitada.
* **Pré-condições:** Uma sessão ativa pausada e aguardando entrada do usuário (`clarification_question` preenchido no checkpointer).

```
[ Espaço em Branco — A completar com a lógica de recuperação e retoma do grafo ]
```

---

### UC08: Ingestão e Processamento de PDFs
* **Objetivo:** Processar um novo PDF gnóstico offline, extrair o texto, gerar chunks com LlamaIndex, extrair metadados (câmara de acesso) e persistir vetores no Qdrant.
* **Pré-condições:** Arquivos PDF no repositório local, credenciais corretas do Qdrant e Gemini.

```
[ Espaço em Branco — A completar com as regras de chunking e validação de páginas ]
```

---

### UC09: Controle de Limites e Assinatura
* **Objetivo:** Bloquear novas perguntas ao RAG se o usuário ultrapassar os limites semanais/mensais do seu plano de assinatura (FREE, BASIC, PREMIUM).
* **Pré-condições:** Usuário autenticado enviando uma nova requisição ao chat.

```
[ Espaço em Branco — A completar com as regras de limite do plano ]
```
