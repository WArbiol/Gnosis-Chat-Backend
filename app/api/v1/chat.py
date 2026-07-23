import json
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.core.dependencies import get_supabase_client
from app.schemas.chat import ChatRequest, UIFilters
from app.schemas.user import UserProfile
from app.domain.exceptions import QuotaExceededException
from app.core.limiter import limiter
from app.services.conversation_service import ConversationService
from app.api.v1.conversations import get_conversation_service

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

from app.agents.nodes.utils import get_llm, get_vector_store, get_reranker

def get_llm_gateway() -> GeminiLLM:
    return get_llm()

def get_vector_store_gateway() -> QdrantVectorStore:
    return get_vector_store()

def get_reranker_gateway() -> VertexRanking:
    return get_reranker()

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
@limiter.limit("20/minute")
async def ask(
    request: Request,
    payload: ChatRequest,
    background_tasks: BackgroundTasks,
    user: UserProfile = Depends(get_current_user),
    use_case: AskRagUseCase = Depends(get_ask_rag_use_case),
    conv_service: ConversationService = Depends(get_conversation_service)
):
    """Realiza uma pergunta ao chat e inicia o fluxo RAG agêntico via Server-Sent Events (SSE)."""
    
    # Verifica se a conversa é nova para gerar título inteligente
    if payload.conversation_id:
        try:
            conv = conv_service.get_conversation(str(payload.conversation_id))
            # Se for a primeira mensagem (0 ou 1 dependendo se o flutter salvou), ou se chama "Nova conversa"
            if conv.title == "Nova conversa":
                background_tasks.add_task(
                    conv_service.generate_title_async,
                    str(payload.conversation_id),
                    payload.query
                )
        except Exception as e:
            logger.warning(f"Erro ao verificar título da conversa {payload.conversation_id}: {e}")

    
    async def event_generator():
        try:
            async for event in use_case.execute(
                query=payload.query,
                user_id=user.id,
                ui_filters=payload.ui_filters or UIFilters(),
                user_profile=user,
                conversation_id=str(payload.conversation_id) if payload.conversation_id else None
            ):
                event_name = event.get("event", "message")
                yield f"event: {event_name}\ndata: {json.dumps(event)}\n\n"
        except QuotaExceededException as qe:
            error_payload = {
                "event": "error",
                "code": "PAYMENT_REQUIRED",
                "message": str(qe)
            }
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
        except Exception as e:
            logger.error(f"Erro no streaming do RAG: {e}", exc_info=True)
            error_payload = {
                "event": "error",
                "code": "INTERNAL_ERROR",
                "message": "Ocorreu um erro interno ao processar sua pergunta."
            }
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

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
                event_name = event.get("event", "message")
                yield f"event: {event_name}\ndata: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error(f"Erro no streaming da clarificação HIL: {e}", exc_info=True)
            error_payload = {
                "event": "error",
                "code": "INTERNAL_ERROR",
                "message": "Ocorreu um erro ao retomar o processamento da clarificação."
            }
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
