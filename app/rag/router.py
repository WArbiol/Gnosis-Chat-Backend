from app.rag.state import GraphState

ROUTER_PROMPT = """You are a query classifier for a gnostic knowledge chat system.
Analyze the user's question and classify it into exactly ONE category:

- RAG_BOOKS: The question is about gnostic texts, hermetic philosophy, esoteric spirituality,
  or any topic that requires searching the PDF corpus.
- RAG_USER: The question is about the user's personal interests, preferences, or past topics
  they've explored.
- RAG_BOTH: The question combines personal context with gnostic knowledge
  (e.g., "based on my interests, what should I read next?").
- DIRECT: The question is generic, a greeting, or does not require any document search
  (e.g., "hello", "who are you?", "what can you do?").

Respond with ONLY the category name, nothing else.

Question: {query}
Category:"""


async def route_query(state: GraphState) -> GraphState:
    """LangGraph node: classify query using Gemini Flash.

    TODO: wire Gemini Flash API call with ROUTER_PROMPT
    """
    query = state["query"]

    # TODO: call Gemini Flash with ROUTER_PROMPT.format(query=query)
    # TODO: parse response and set route
    route = "RAG_BOOKS"  # default fallback

    return {**state, "route": route}
