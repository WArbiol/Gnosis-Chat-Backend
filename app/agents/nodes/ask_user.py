from typing import Any
from app.agents.state import GraphState

from langchain_core.runnables import RunnableConfig

async def ask_user_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Nó que prepara a pergunta esclarecedora de HIL."""
    question = state.get("clarification_question", "Poderia esclarecer melhor a sua pergunta?")
    
    # Marcamos a resposta com a pergunta para que o frontend saiba que é HIL
    return {
        "answer": f"PAUSE_HIL: {question}",
        "citations": []
    }
