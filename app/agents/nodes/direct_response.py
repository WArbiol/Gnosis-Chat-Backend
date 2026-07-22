from typing import Any
from app.agents.state import GraphState

from langchain_core.runnables import RunnableConfig

async def direct_response_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Nó para resposta direta rápida (ex: saudações), pulando o fluxo de RAG."""
    direct_answer = state.get("direct_answer", "Como posso te ajudar hoje?")
    return {
        "answer": direct_answer,
        "citations": []
    }
