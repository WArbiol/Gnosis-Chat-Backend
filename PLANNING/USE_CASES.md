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

#### Fluxo Principal de Sucesso:
1. O cliente (Flutter) faz uma chamada HTTP POST para `/api/v1/conversations/{id}/ask` passando a `query` e filtros opcionais na UI (`ui_filters` contendo `book_name`, `author`, `chamber`, `chapter`).
2. O middleware do backend FastAPI valida o token JWT do usuário, resolve o `user_id` e verifica as cotas do plano.
3. O FastAPI inicializa o grafo do LangGraph, salvando no `GraphState` os filtros iniciais `ui_filters` e passando a câmara de acesso do usuário (`chamber_level`) como restrição intransponível.
4. **Nó 1: Orchestrator** analisa a query e resolve os metadados de filtro:
   - *Filtros Implícitos:* Extrai referências a livros, autores ou capítulos escritas na query do usuário.
   - *Filtros Autônomos:* Se deduzir que a resposta depende de um livro ou contexto específico, injeta esses filtros de forma autônoma para refinar o retrieval.
   - Consolida as restrições e as armazena no campo `metadata_filters` do estado do grafo.
   - Determina se a pergunta necessita de RAG (se sim, gera sub-queries para rotear ao Researcher; se não, decide a rota `DIRECT_RESPONSE`).
5. **Nó 2: Researcher(s)** (podendo rodar em paralelo se houver múltiplas sub-queries):
   - Cada instância aplica os `metadata_filters` consolidados para filtrar os chunks no Qdrant.
   - Executa a busca vetorial para retornar ~30 chunks e os envia para a Vertex AI Ranking API para re-ranking, mantendo os top ~10 mais relevantes.
6. **Nó 3: Critique** valida a relevância e suficiência dos chunks. Se aprovado, o Orchestrator avança para o Writer.
7. **Nó 4: Writer** redige a resposta final baseada nos chunks e constrói as citações.
8. **Nó 5: Judge** realiza a auditoria contra alucinações e valida as citações de páginas do PDF. Se aprovado, avança para o Recap.
9. **Nó 6: Recap** resume a resposta final em 2 a 3 frases.
10. O backend retorna a resposta via **SSE (Server-Sent Events)** contendo:
    - Eventos do tipo `status` transmitindo a transição dos nós.
    - Eventos do tipo `token` enviando a escrita em tempo real.
    - Evento do tipo `final` contendo a resposta consolidada, citação completa dos PDFs (com signed URLs) e recap.

#### Fluxo Alternativo (Filtros Sem Correspondência ou Contexto Insuficiente):
* Se os filtros aplicados (explícitos ou autônomos) forem tão restritivos que não tragam chunks suficientes, o Critique detecta a insuficiência e envia feedback ao Orchestrator.
* O Orchestrator pode relaxar os filtros autônomos nas tentativas subsequentes (até 2 loops de pesquisa adicionais).
* Se ainda assim falhar, o Writer emite a resposta fallback padrão: *"Não há referências sobre isso no corpus literário"*.

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
