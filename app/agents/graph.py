from typing import Literal
from langgraph.graph import StateGraph, END
from app.agents.state import GraphState
from app.agents.nodes.orchestrator import orchestrator_node
from app.agents.nodes.researcher import researcher_node
from app.agents.nodes.critique import critique_node
from app.agents.nodes.writer import writer_node
from app.agents.nodes.judge import judge_node
from app.agents.nodes.recap import recap_node
from app.agents.nodes.direct_response import direct_response_node
from app.agents.nodes.ask_user import ask_user_node

def route_from_orchestrator(state: GraphState) -> Literal["researcher", "writer", "direct_response", "ask_user"]:
    """Determina a próxima rota a partir da decisão do orquestrador."""
    return state.get("next_step", "direct_response")

def route_from_critique(state: GraphState) -> Literal["orchestrator"]:
    """Retorna sempre ao orquestrador para avaliar a suficiência e decidir a próxima ação."""
    return "orchestrator"

def route_from_judge(state: GraphState) -> Literal["recap", "orchestrator"]:
    """Roteia para recap se aprovado pelo Judge, ou volta ao orquestrador para feedback se rejeitado."""
    verdict = state.get("judge_verdict", "approved")
    if verdict == "approved":
        return "recap"
    return "orchestrator"

def build_agentic_rag_graph():
    """Compila o grafo do LangGraph com os 8 nós especialistas de RAG."""
    # 1. Instanciar o StateGraph com a estrutura de estado GraphState
    builder = StateGraph(GraphState)

    # 2. Registrar todos os nós especialistas
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("researcher", researcher_node)
    builder.add_node("critique", critique_node)
    builder.add_node("writer", writer_node)
    builder.add_node("judge", judge_node)
    builder.add_node("recap", recap_node)
    builder.add_node("direct_response", direct_response_node)
    builder.add_node("ask_user", ask_user_node)

    # 3. Ponto de entrada
    builder.set_entry_point("orchestrator")

    # 4. Configurar as arestas condicionais e transições
    builder.add_conditional_edges(
        "orchestrator",
        route_from_orchestrator,
        {
            "researcher": "researcher",
            "writer": "writer",
            "direct_response": "direct_response",
            "ask_user": "ask_user"
        }
    )

    # Do Researcher flui direto ao Critique
    builder.add_edge("researcher", "critique")

    # Do Critique volta condicionalmente (ou incondicionalmente via router) ao Orchestrator
    builder.add_conditional_edges(
        "critique",
        route_from_critique,
        {
            "orchestrator": "orchestrator"
        }
    )

    # Do Writer flui direto ao Recap (bypassing Judge para economia de tokens)
    builder.add_edge("writer", "recap")

    # Nós de saída finalizam a execução
    builder.add_edge("recap", END)
    builder.add_edge("direct_response", END)
    builder.add_edge("ask_user", END)

    return builder

# Compila o grafo global com o checkpointer resolvido da factory
from app.infrastructure.langgraph.checkpointer import CheckpointerFactory
compiled_graph = build_agentic_rag_graph().compile(
    checkpointer=CheckpointerFactory.get_checkpointer()
)
