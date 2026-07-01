import json
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.core.dependencies import get_supabase_client
from app.schemas.chat import ChatRequest, UIFilters
from app.schemas.user import UserProfile
from app.domain.exceptions import QuotaExceededException

# Use Cases
from app.application.use_cases.ask_rag_use_case import AskRagUseCase
from app.application.use_cases.clarify_use_case import ClarifyUseCase

# Adapters
from app.infrastructure.google.gemini_llm import GeminiLLM
from app.infrastructure.qdrant.qdrant_vector_store import QdrantVectorStore
from app.infrastructure.google.vertex_ranking import VertexRanking
from app.infrastructure.supabase.supabase_database import SupabaseDatabase

logger = logging.getLogger(__name__)
router = APIRouter()

# Instanciar adaptadores de forma preguiçosa (Lazy) ou via dependências
_llm_gateway = None
_vector_store_gateway = None
_reranker_gateway = None

def get_llm_gateway() -> GeminiLLM:
    global _llm_gateway
    if _llm_gateway is None:
        _llm_gateway = GeminiLLM()
    return _llm_gateway

def get_vector_store_gateway() -> QdrantVectorStore:
    global _vector_store_gateway
    if _vector_store_gateway is None:
        _vector_store_gateway = QdrantVectorStore()
    return _vector_store_gateway

def get_reranker_gateway() -> VertexRanking:
    global _reranker_gateway
    if _reranker_gateway is None:
        _reranker_gateway = VertexRanking()
    return _reranker_gateway

def get_ask_rag_use_case(
    llm: GeminiLLM = Depends(get_llm_gateway),
    vector_store: QdrantVectorStore = Depends(get_vector_store_gateway),
    reranker: VertexRanking = Depends(get_reranker_gateway),
    supabase_client = Depends(get_supabase_client)
) -> AskRagUseCase:
    database_gateway = SupabaseDatabase(supabase_client)
    return AskRagUseCase(
        llm=llm,
        vector_store=vector_store,
        reranker=reranker,
        database=database_gateway
    )

def get_clarify_use_case(
    llm: GeminiLLM = Depends(get_llm_gateway),
    vector_store: QdrantVectorStore = Depends(get_vector_store_gateway),
    reranker: VertexRanking = Depends(get_reranker_gateway),
    supabase_client = Depends(get_supabase_client)
) -> ClarifyUseCase:
    database_gateway = SupabaseDatabase(supabase_client)
    return ClarifyUseCase(
        llm=llm,
        vector_store=vector_store,
        reranker=reranker,
        database=database_gateway
    )

class ClarifyRequest(BaseModel):
    """Payload de entrada para responder ao Human-in-the-Loop."""
    conversation_id: UUID = Field(..., description="ID da conversa sob intervenção.")
    user_response: str = Field(..., min_length=1, max_length=2000, description="Texto de resposta de esclarecimento.")

@router.post("/ask")
async def ask(
    request: ChatRequest,
    user: UserProfile = Depends(get_current_user),
    use_case: AskRagUseCase = Depends(get_ask_rag_use_case)
):
    """Realiza uma pergunta ao chat e inicia o fluxo RAG agêntico via Server-Sent Events (SSE)."""
    
    async def event_generator():
        try:
            async for event in use_case.execute(
                query=request.query,
                user_id=user.id,
                ui_filters=request.ui_filters or UIFilters(),
                conversation_id=str(request.conversation_id) if request.conversation_id else None
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except QuotaExceededException as qe:
            error_payload = {
                "event": "error",
                "code": "PAYMENT_REQUIRED",
                "message": str(qe)
            }
            yield f"data: {json.dumps(error_payload)}\n\n"
        except Exception as e:
            logger.error(f"Erro no streaming do RAG: {e}", exc_info=True)
            error_payload = {
                "event": "error",
                "code": "INTERNAL_ERROR",
                "message": "Ocorreu um erro interno ao processar sua pergunta."
            }
            yield f"data: {json.dumps(error_payload)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/clarify")
async def clarify(
    request: ClarifyRequest,
    user: UserProfile = Depends(get_current_user),
    use_case: ClarifyUseCase = Depends(get_clarify_use_case)
):
    """Responde à pergunta clarificadora (HIL) e retoma a execução do grafo em tempo real via SSE."""
    
    async def event_generator():
        try:
            async for event in use_case.execute(
                conversation_id=str(request.conversation_id),
                user_response=request.user_response,
                user_id=user.id
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error(f"Erro no streaming da clarificação HIL: {e}", exc_info=True)
            error_payload = {
                "event": "error",
                "code": "INTERNAL_ERROR",
                "message": "Ocorreu um erro ao retomar o processamento da clarificação."
            }
            yield f"data: {json.dumps(error_payload)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
