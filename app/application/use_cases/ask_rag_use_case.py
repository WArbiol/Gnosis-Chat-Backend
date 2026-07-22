import logging
from typing import AsyncGenerator, Any
from app.domain.exceptions import QuotaExceededException
from app.schemas.user import UserProfile, PlanEnum, PlanLimits
from app.schemas.chat import UIFilters
from app.application.interfaces.llm_gateway import LLMGateway
from app.application.interfaces.vector_store_gateway import VectorStoreGateway
from app.application.interfaces.reranker_gateway import RerankerGateway
from app.application.interfaces.database_gateway import DatabaseGateway
from app.agents.graph import compiled_graph

logger = logging.getLogger(__name__)

class AskRagUseCase:
    """Caso de uso de negócio para processar perguntas através do RAG agêntico."""

    def __init__(
        self,
        llm: LLMGateway,
        vector_store: VectorStoreGateway,
        reranker: RerankerGateway,
        database: DatabaseGateway
    ) -> None:
        self.llm = llm
        self.vector_store = vector_store
        self.reranker = reranker
        self.database = database

    async def execute(
        self,
        query: str,
        user_id: str,
        ui_filters: UIFilters,
        user_profile: UserProfile,
        conversation_id: str | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Executa o RAG agêntico em streaming, emitindo eventos parciais e persistindo dados."""
        
        # Validação de cotas baseada no question_count incrementado (perguntas bem sucedidas)
        limit = PlanLimits.get_question_limit(user_profile.plan)
        if user_profile.question_count >= limit:
            if user_profile.plan == PlanEnum.FREE:
                raise QuotaExceededException(
                    "Você atingiu o limite de 3 perguntas do plano Gratuito. Faça o upgrade para continuar explorando o conhecimento gnóstico livremente.",
                    code="LIMIT_EXCEEDED"
                )
            else:
                raise QuotaExceededException(
                    f"Você atingiu o limite de {limit} mensagens mensais do plano {user_profile.plan.value.upper()}.",
                    code="LIMIT_EXCEEDED"
                )

        # 2. Criar ou validar ID da conversa
        if not conversation_id:
            # Criamos uma nova conversa mock que o usuário verá no Flutter
            # Para o MVP do RAG, o backend apenas gera o ID se não vier nada
            import uuid
            conversation_id = str(uuid.uuid4())
            # Idealmente salvamos no banco de conversas
            # Mas como o Flutter faz o CRUD pelo Supabase SDK diretamente, 
            # garantimos que temos um ID válido para persistir mensagens
        
        # 3. Salvar a pergunta do usuário no banco de forma otimista
        await self.database.save_message(
            conversation_id=conversation_id,
            role="user",
            content=query
        )

        # 4. Configurar estado inicial do grafo, limpando o estado da rodada anterior
        initial_state = {
            "query": query,
            "user": user_profile.model_dump() if user_profile else {},
            "ui_filters": ui_filters.model_dump() if ui_filters else {},
            "conversation_history": await self.database.get_recent_messages(conversation_id, limit=10) if conversation_id else [],
            "session_counters": {
                "researcher_calls": 0,
                "critique_loops": 0,
                "judge_loops": 0,
                "ask_user_calls": 0
            },
            # Limpar chaves da rodada anterior para evitar reuso indevido do checkpoint
            "next_step": None,
            "sub_queries": [],
            "orchestrator_checklist": {},
            "research_results": [],
            "metadata_filters": {},
            "critique_verdict": None,
            "critique_feedback": None,
            "answer": "",
            "citations": [],
            "judge_verdict": None,
            "judge_feedback": None,
            "recap": "",
            "chamber_warning": None,
            "direct_answer": None,
            "clarification_question": None,
            "user_clarification": None
        }

        # Configurações de runtime injetando gateways via Clean Architecture
        config = {
            "configurable": {
                "thread_id": conversation_id,
                "llm": self.llm,
                "vector_store": self.vector_store,
                "reranker": self.reranker,
                "database": self.database
            },
            "recursion_limit": 50
        }

        # 5. Executar o grafo em streaming de eventos
        final_state = {}
        
        try:
            async for event in compiled_graph.astream_events(
                initial_state,
                config=config,
                version="v2"
            ):
                event_type = event.get("event")
                node_name = event.get("metadata", {}).get("langgraph_node")

                # Transições de nós (Status)
                if event_type == "on_chain_start" and event.get("name") == "LangGraph":
                    yield {
                        "event": "status",
                        "agent": "orchestrator",
                        "message": "Inicializando orquestração..."
                    }
                
                elif event_type == "on_chain_start" and event.get("name") in [
                    "orchestrator", "researcher", "critique", "writer", "judge", "recap", "direct_response", "ask_user"
                ]:
                    node = event.get("name")
                    msg = "Processando..."
                    if node == "orchestrator":
                        msg = "Orquestrador decidindo próximos passos..."
                    elif node == "researcher":
                        msg = "Pesquisadores vasculhando o corpus de PDFs no Qdrant..."
                    elif node == "critique":
                        msg = "Critique avaliando a qualidade dos trechos encontrados..."
                    elif node == "writer":
                        msg = "Writer redigindo a resposta detalhada..."
                    elif node == "judge":
                        msg = "Judge auditando a resposta contra alucinações..."
                    elif node == "recap":
                        msg = "Recap sintetizando a resposta..."
                    elif node == "direct_response":
                        msg = "Gerando resposta rápida..."
                    elif node == "ask_user":
                        msg = "Aguardando esclarecimentos..."

                    yield {
                        "event": "status",
                        "agent": node,
                        "message": msg
                    }

                # Streaming de tokens do Writer via evento customizado
                elif event_type == "on_custom_event" and event.get("name") == "writer_token":
                    text = event.get("data", {}).get("text")
                    if text:
                        yield {
                            "event": "token",
                            "text": text
                        }

                # Coletar estado final ao término de cada nó
                elif event_type == "on_chain_end" and event.get("name") == "LangGraph":
                    final_state = event.get("data", {}).get("output", {})

            # 6. Processamento pós-grafo (Persistir Resposta e Citações)
            answer = final_state.get("answer", "")
            citations = final_state.get("citations") or []
            recap = final_state.get("recap", "")
            next_step = final_state.get("next_step")

            # Se houver aviso de câmara restrita, anexar ao final da resposta
            chamber_warning = final_state.get("chamber_warning")
            if chamber_warning and answer:
                answer = f"{answer}\n\n{chamber_warning}"

            # Tratar caso de Human-in-the-Loop
            is_hil = next_step == "ask_user" or answer.startswith("PAUSE_HIL:")
            
            suggested_followups = final_state.get("suggested_followups") or []

            # Se não for HIL, persistir e descontar cota
            if not is_hil:
                # Salvar mensagem gerada pelo RAG no Supabase com o resumo (recap) formatado em blockquote
                db_content = answer
                if recap:
                    db_content = f"{answer}\n\n> {recap}"
                msg_id = await self.database.save_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=db_content,
                    route=final_state.get("next_step", "RAG"),
                    token_count=len(db_content.split()),
                    suggested_followups=suggested_followups
                )
                
                # Salvar citações
                if citations:
                    await self.database.save_citations(msg_id, citations)
                
                # Incrementar contador de perguntas do usuário
                await self.database.increment_user_question_count(user_id)
            else:
                # HIL: Salva como mensagem do assistente mas sinaliza que é pergunta clarificadora
                clean_question = answer.replace("PAUSE_HIL: ", "")
                await self.database.save_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=clean_question,
                    route="ASK_USER"
                )

            suggested_followups = final_state.get("suggested_followups") or []

            # Emitir evento final completo (garantindo que o prefixo interno PAUSE_HIL seja removido)
            clean_answer = answer.replace("PAUSE_HIL: ", "") if is_hil else answer
            yield {
                "event": "final",
                "answer": clean_answer,
                "citations": [cit.model_dump() for cit in citations],
                "recap": recap,
                "suggested_followups": suggested_followups,
                "conversation_id": conversation_id,
                "is_hil": is_hil
            }

        except Exception as e:
            logger.error(f"Erro na execução do RAG agêntico: {e}", exc_info=True)
            yield {
                "event": "error",
                "message": f"Erro interno no processamento: {str(e)}"
            }
