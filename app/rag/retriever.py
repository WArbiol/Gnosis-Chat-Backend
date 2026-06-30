from app.rag.filters import build_book_filters, build_interest_filters
from app.rag.state import GraphState
from app.schemas.chat import Citation


async def retrieve(state: GraphState) -> GraphState:
    """LangGraph node: retrieve relevant chunks based on route.

    Routes to the appropriate Qdrant collection(s) via LlamaIndex.
    """
    route = state.get("route", "RAG_BOOKS")
    user = state["user"]
    query = state["query"]

    chunks: list[str] = []
    citations: list[Citation] = []

    if route in ("RAG_BOOKS", "RAG_BOTH"):
        book_chunks, book_citations = await _retrieve_books(query, user.chamber_level)
        chunks.extend(book_chunks)
        citations.extend(book_citations)

    if route in ("RAG_USER", "RAG_BOTH"):
        interest_chunks = await _retrieve_interests(query, user.id)
        chunks.extend(interest_chunks)

    return {**state, "chunks": chunks, "citations": citations}


async def _retrieve_books(query: str, chamber_level: int) -> tuple[list[str], list[Citation]]:
    """Retrieve from gnosis_books collection with chamber_level filtering.

    TODO: wire LlamaIndex QdrantVectorStore + GeminiEmbedding
    """
    filters = build_book_filters(chamber_level)
    # TODO: vector_store.aretrieve(query, filters=filters)
    return [], []


async def _retrieve_interests(query: str, user_id: str) -> list[str]:
    """Retrieve from user_interests collection filtered by user_id.

    TODO: wire LlamaIndex QdrantVectorStore with user_id payload filter
    """
    filters = build_interest_filters(user_id)
    # TODO: vector_store.aretrieve(query, filters=filters)
    return []
