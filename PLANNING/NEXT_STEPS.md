ws**/*/*/*//////////////////////////////////////////////////*

# Próximos Passos (Roadmap de Desenvolvimento)

Este documento mapeia as ações necessárias para evoluir o **Gnosis Chat** a partir do estado atual da API do backend.

---

## 🚀 Fase 1: Integração com o Frontend (Flutter)

A prioridade imediata é fazer o aplicativo Flutter consumir os novos endpoints de streaming estruturado.

### 1. Cliente SSE (Server-Sent Events) no Flutter

* Implementar ou adaptar o cliente HTTP no Flutter usando um pacote compatível com streaming SSE (ex: `flutter_client_sse` ou `dio` com `ResponseBody`).
* Conectar nos novos endpoints:
  * `POST /api/v1/chat/ask`
  * `POST /api/v1/chat/clarify`

### 2. Tratamento Visual do Estado dos Agentes

* **Mensagens de Status:** Capturar os eventos `status` emitidos pelo SSE (`"agent": "researcher"`, `"message": "..."`) e exibi-los na interface (ex: um loader dinâmico mostrando "Pesquisando nos livros...", "Garantindo precisão da resposta...").
* **Streaming de Resposta:** Capturar os eventos `token` para renderizar a resposta da IA de forma fluida (efeito máquina de escrever).
* **Citações e Resumo:** Capturar o payload `final` estruturado para renderizar os cards de fontes citadas abaixo da resposta e o resumo (`recap`) no topo ou expandido na bolha.

### 3. Interface de Clarificação (Human-in-the-Loop)

* Tratar a flag `is_hil: true` no payload de retorno.
* Quando `is_hil` for verdadeiro, desabilitar o input regular de chat e exibir a pergunta clarificadora como uma mensagem especial do sistema.
* Enviar a resposta do usuário para o endpoint `/clarify` em vez do `/ask`, mantendo o mesmo `conversation_id`.

---

## 💾 Fase 2: Persistência de Estado do Grafo (Checkpointer)

Atualmente, o LangGraph está configurado para usar o `MemorySaver` (checkpointer em memória RAM).

> [!WARNING]
> Se o servidor do FastAPI for reiniciado, todo o histórico recente e estados de HIL pausados na memória serão perdidos.

### Ações:

* Implementar um checkpointer persistente em banco.
* **Opção Postgres:** Usar `postgres-checkpointer` conectando diretamente ao banco PostgreSQL do Supabase.
* **Opção Supabase Database:** Implementar uma classe que herde de `BaseCheckpointSaver` do LangGraph, salvando e lendo os checkpoints serializados diretamente em uma tabela do Supabase (`langgraph_checkpoints`).

---

## 🧠 Fase 3: Engenharia de Prompts & Refinamento de RAG

Ajustar a qualidade teológica e esotérica das respostas e buscas.

### 1. Instruções Específicas do Orchestrator

* Refinar a habilidade do orquestrador em traduzir queries em linguagem natural em filtros precisos de metadados (`books`, `authors`, `chamber_levels`).
* Validar se o filtro de câmara (`chamber_level` do perfil do usuário) está limitando perfeitamente a visibilidade de conteúdos restritos do Qdrant.

### 2. Tom e Profundidade do Writer

* Personalizar o prompt do `Writer` para responder sob a identidade esotérica correta (linguagem respeitosa, profunda, objetiva e referenciada nas obras gnósticas).

---

## 📈 Fase 4: Observabilidade & CI/CD

Garantir o monitoramento e a saúde da aplicação em ambiente de produção.

### 1. LangSmith Integration

* Garantir que a chave `LANGCHAIN_API_KEY` esteja ativa no arquivo `.env` de staging/produção para monitorar o custo de tokens, tempo de latência de cada nó e histórico de execuções.

### 2. CI/CD Pipeline

* Adicionar uma etapa de teste no GitHub Actions para rodar a suíte local de testes automaticamente a cada Pull Request ou Commit na branch principal:
  ```bash
  uv run pytest
  ```

