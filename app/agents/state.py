from typing import TypedDict, Literal, Any
from pydantic import BaseModel
from app.schemas.user import UserProfile
from app.schemas.chat import UIFilters
from app.schemas.conversation import CitationResponse

class ResearchResult(TypedDict):
    """Resultado de uma pesquisa individual do Researcher."""
    sub_query: str
    chunks: list[str]
    citations: list[CitationResponse]
    relevance_scores: list[float]

class SessionCounters(TypedDict):
    """Contadores de controle para evitar loops infinitos na sessão."""
    researcher_calls: int
    critique_loops: int
    judge_loops: int
    ask_user_calls: int

class GraphState(TypedDict, total=False):
    """Estado persistido compartilhado entre os nós do LangGraph."""
    # --- Input ---
    query: str                          # Pergunta inicial do usuário
    user: UserProfile                   # Objeto do perfil do usuário autenticado
    ui_filters: UIFilters               # Filtros explícitos vindos do Flutter (books, authors, chamber_levels, chapters)
    conversation_history: list[dict[str, Any]]  # Histórico recente da conversa (sliding window)

    # --- Orchestrator ---
    sub_queries: list[str]              # Queries decompostas para pesquisar
    next_step: str                      # Próximo nó decidido pelo orquestrador
    orchestrator_checklist: dict[str, Any] # Checklist de sub-queries e etapas
    session_counters: SessionCounters   # Contadores de limite da sessão

    # --- Researcher ---
    research_results: list[ResearchResult] # Resultados agregados de cada Researcher
    metadata_filters: dict[str, Any]    # Filtros de metadados consolidados (UI + inferidos)

    # --- Critique ---
    critique_verdict: Literal["sufficient", "insufficient"]
    critique_feedback: str              # Feedback detalhado de onde a pesquisa falhou

    # --- Writer ---
    answer: str                         # Resposta final redigida
    citations: list[CitationResponse]   # Citações com metadados extraídos

    # --- Judge ---
    judge_verdict: Literal["approved", "rejected"]
    judge_feedback: str                 # Feedback detalhado caso a resposta seja reprovada

    # --- Recap ---
    recap: str                          # Resumo conciso de 2-3 frases

    # --- Direct Response ---
    direct_answer: str                  # Resposta rápida (para saudações ou fora de escopo)

    # --- Human-in-the-Loop ---
    clarification_question: str         # Pergunta clarificadora gerada pelo Ask User
    user_clarification: str             # Resposta de esclarecimento fornecida pelo usuário
