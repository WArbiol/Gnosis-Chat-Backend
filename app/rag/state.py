from typing import TypedDict

from app.schemas.chat import Citation
from app.schemas.user import UserProfile


class GraphState(TypedDict, total=False):
    """Typed state for the LangGraph RAG pipeline.

    Each key represents data flowing between graph nodes.
    """

    # Input
    query: str
    user: UserProfile

    # Router output
    route: str  # RAG_BOOKS | RAG_USER | RAG_BOTH | DIRECT

    # Retriever output
    chunks: list[str]
    citations: list[Citation]

    # Synthesizer output
    answer: str

    # Interest tracker
    inferred_interests: list[str]
