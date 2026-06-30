from app.rag.retriever import retrieve
from app.rag.router import route_query
from app.rag.state import GraphState
from app.rag.synthesizer import synthesize


def build_rag_graph():
    """Build and compile the LangGraph RAG pipeline.

    Graph: router_node → retriever_node → synthesizer_node

    TODO: wire actual LangGraph StateGraph
    """
    # TODO: uncomment when langgraph is wired
    # from langgraph.graph import StateGraph
    #
    # graph = StateGraph(GraphState)
    #
    # graph.add_node("router", route_query)
    # graph.add_node("retriever", retrieve)
    # graph.add_node("synthesizer", synthesize)
    #
    # graph.add_edge("router", "retriever")
    # graph.add_edge("retriever", "synthesizer")
    #
    # graph.set_entry_point("router")
    # graph.set_finish_point("synthesizer")
    #
    # return graph.compile()

    return None  # placeholder until wired


compiled_graph = build_rag_graph()
