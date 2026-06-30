from app.rag.state import GraphState

SYNTHESIS_PROMPT = """You are Gnosis, an expert in gnostic texts, hermetic philosophy,
and esoteric spirituality. Answer the user's question based ONLY on the provided context.

Rules:
- Cite sources using [PDF_NAME, p.PAGE] format
- If the context is insufficient, say so honestly
- Respond in the same language as the user's question
- Be precise and scholarly, yet accessible

Context:
{context}

Question: {query}

Answer:"""


async def synthesize(state: GraphState) -> GraphState:
    """LangGraph node: generate answer from retrieved chunks using Gemini Flash.

    TODO: wire Gemini 2.5 Flash API call with SYNTHESIS_PROMPT
    """
    query = state["query"]
    chunks = state.get("chunks", [])
    route = state.get("route", "DIRECT")

    if route == "DIRECT" or not chunks:
        return {
            **state,
            "answer": "TODO: direct response without RAG context",
        }

    context = "\n\n---\n\n".join(chunks)

    # TODO: call Gemini Flash with SYNTHESIS_PROMPT.format(context=context, query=query)
    # TODO: parse citations from response

    return {
        **state,
        "answer": "TODO: synthesizer not yet wired",
    }
