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
1. O cliente (Flutter) faz uma chamada HTTP POST para `/api/v1/conversations/{id}/ask` passando a `query` e filtros opcionais na UI (`ui_filters` contendo `books`, `authors`, `chamber_levels`, `chapters`).
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
* **Objetivo:** Retomar o processamento do grafo que foi pausado pelo nó `Ask User` após o usuário fornecer a informação solicitada.
* **Pré-condições:** Uma sessão ativa pausada e aguardando entrada do usuário (com o estado da sessão persistido no PostgresSaver/Supabase via `thread_id`).

#### Fluxo Principal de Sucesso:
1. O usuário visualiza no app a pergunta clarificadora gerada anteriormente pelo RAG (ex: *"Você quer saber sobre o Selo de Salomão ou o Selo do Apocalipse?"*).
2. O usuário envia sua resposta (ex: *"Selo de Salomão"*).
3. O cliente (Flutter) dispara uma requisição HTTP POST para `/api/v1/conversations/{id}/clarify` enviando a resposta textual.
4. O backend FastAPI recebe a resposta e o `thread_id` (vinculado ao `conversation_id`).
5. O FastAPI busca no checkpointer do Postgres o estado salvo do grafo para essa conversa específica (`thread_id`).
6. O estado é carregado e a resposta do usuário é injetada em um campo temporário do `GraphState` (ex: `user_clarification`).
7. O backend envia um sinal para o LangGraph retomar a execução (`compiled_graph.update_state` seguido de continuação da execução).
8. **Nó 1: Orchestrator** é re-executado:
   - Lê a resposta do usuário em `user_clarification`.
   - Modifica os `metadata_filters` baseados na escolha do usuário (ex: limita `books` ou adiciona palavras-chave específicas).
   - Avança para o nó **Researcher** para retomar o fluxo padrão de RAG com o contexto agora limpo e sem ambiguidade.
9. O processamento prossegue até o final do grafo normalmente (Critique ➔ Writer ➔ Judge ➔ Recap ➔ END).
10. O fluxo retorna via streaming de SSE até a conclusão.

#### Fluxo de Exceção (Abandono):
* Se o usuário decidir não responder à pergunta esclarecedora e simplesmente digitar uma nova pergunta completamente diferente no chat, o Flutter detecta isso e chama o endpoint padrão `/ask` (UC01) criando um novo turno limpo (uma nova sessão no LangGraph), o que sobrescreve o checkpoint pausado anteriormente.

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

#### Regras de Cotas (Lógica de Negócio):
1. **Plano Free (Gratuito):**
   - **Limite:** 3 perguntas por semana.
   - **Mecanismo:** Calculado dinamicamente no banco fazendo um `COUNT` das mensagens do usuário criadas nos últimos 7 dias. Não requer cronjob para reset.
2. **Plano Básico:**
   - **Limite:** 100 perguntas por mês.
   - **Mecanismo:** Campo `question_count` na tabela de usuários do Supabase. O faturamento e o ciclo de reset são controlados pelo Stripe.
3. **Plano Premium:**
   - **Limite:** 1.000 perguntas por mês.
   - **Mecanismo:** Campo `question_count` na tabela de usuários do Supabase.

#### Ciclo de Reset das Cotas:
* **Reset por Faturamento (Básico/Premium):** Quando o webhook do Stripe reporta renovação de assinatura com sucesso (`invoice.paid`) ou upgrade de plano (`customer.subscription.updated`), a coluna `question_count` do usuário é resetada para `0` no Supabase.
* **Downgrade:** Se o usuário cancela ou deixa de pagar, o webhook do Stripe altera o plano para `free`. A partir desse momento, aplica-se a regra dinâmica de 3 perguntas por semana.

#### Fluxo de Enforcamento (Middleware / Endpoint `/ask`):
1. O usuário submete uma pergunta (`POST /conversations/{id}/ask`).
2. O validador do backend FastAPI lê o perfil do usuário (`UserProfile`) e verifica se `plan` e limites são compatíveis:
   - Se `plan == "free"`: Faz query para contar mensagens nos últimos 7 dias. Se count >= 3, **bloqueia**.
   - Se `plan in ("basic", "premium")`: Se `question_count` >= limite do plano, **bloqueia**.
3. **Mapeamento de Erro HTTP:**
   - Em caso de bloqueio, o FastAPI retorna **HTTP 402 Payment Required** com um corpo padronizado:
     ```json
     {
       "detail": "Limite de mensagens atingido para o plano atual.",
       "code": "LIMIT_EXCEEDED",
       "plan": "free"
     }
     ```
   - O app Flutter intercepta o HTTP 402 e exibe automaticamente o modal de upgrade (`subscription_screen.dart`).
4. Se o limite não foi excedido, o processamento do grafo segue e, após a execução com sucesso do Writer/Judge, o contador `question_count` é incrementado em 1.
