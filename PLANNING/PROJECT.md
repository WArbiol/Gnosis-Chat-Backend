Para considerar:

- Uso de Re-Rank com CrossEncoder (RAG trás 30 Documentos e o CrossEncoder filtra os principais e não lota o contexto do agente Writer)
  - Se for muito poucos o agentic RAG reformula a pergunta

- Planejamento do Agentic RAG
  - Realizar um Diagrama do LangGraph ou pensar em um nó agêntico para usar CrewAI ou smolagent (vamos discutir)
  - Temos que ter pelo menos: Planner, Researcher, Writer, Critic (e vamos discutir se precisamos de um Judge)
  - Só para o Researcher deveremos ter:
    - Query Transformation (para melhorar e reccal e a qualidade dos dados - adiciona sinônimos, reformula a pergunta, etc) (mas temos que ter cuidado para não modificar a dúvida do usuário)
    - Se for vários assuntos, vamos fazer várias consultas e organizar para dar uma reposta profissional:
      - por exemplo: o usuário pergunta x e y, então fazemos uma RAG para x e uma para y
      - As perguntas da parte do Collaborative Human-in-the-Loop pode ou não resultar em adicionar possíveis queries
    - Meta Data filtering (para melhorar a precisão, vindo da query do usuário ou se ele explicitamentamente filtrou nas configurações)
    - Cross-Encoder Re-Ranking (para melhorar a precisão, pegando os principais documentos) (ver os tradeoffs disso, por ser pesado, ainda vamos ver se vale a pena) (verificar Vertex AI Ranking API ou outras opções que se adequam mais a este projeto) - (buscamos por exemplo 20 fontes e ficamos só com as principais (hardcodado 10 ou a partir de um certo ranking))



---
Ideias:
no início do Researcher podemos ter algo como:
"""
  messages = [
      {
          "role": "system",
          "content": (
              "You are the Researcher agent in a multi-agent system. "
              "Decompose the task, propose sections, and identify evidence angles. "
              "Do NOT write the final narrative; instead, return an outline with bullets."
          ),
      },
      {"role": "user", "content": task},
  ]
"""
(Avalie, existem soluções profissionais e melhores para nosso caso) (necessitamos de planning e reflection)


---
Para o Planner -> talvez tenhamos que realizar mais de um RAG (digamos que a pergunta envolvia vários assuntos), e então como teremos várias Pesquisas faz sentidos termos vários Researchers em paralelo (concorrent)

Esse Planner deve ter um checklist para garantir que todas as etapas foram cumpridas.

- Collaborative Human-in-the-Loop: se algo não for esclarecido, o agente Planner deve fazer perguntas esclarecedoras (mas não deve ser sempre sempre, quando preciso)

---
Para cada sub agente queremos ter os limites claros, por exemplo, apenas o Researcher realizar RAG

Vamos discutir se vale a pena ter "Observe Everything": 
  - Traces (logs)
  - Cost Meters 
  - Replay capability
  (O que não vemos, não podemos consertar)
  - vamos discutir se isso não trará over-engineer para um projeto inicial


---
Vamos discutir também resiliência a falhas, como implementar isso