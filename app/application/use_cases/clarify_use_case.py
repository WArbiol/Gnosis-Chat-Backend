import logging
from typing import AsyncGenerator, Any
from app.application.interfaces.llm_gateway import LLMGateway
from app.application.interfaces.vector_store_gateway import VectorStoreGateway
from app.application.interfaces.reranker_gateway import RerankerGateway
from app.application.interfaces.database_gateway import DatabaseGateway
from app.agents.graph import compiled_graph

logger = logging.getLogger(__name__)

class ClarifyUseCase:
    """Caso de uso para responder a esclarecimentos e retomar a execução do grafo RAG."""

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
        conversation_id: str,
        user_response: str,
        user_id: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Atualiza o estado do checkpoint e retoma a execução do grafo em tempo real."""
        
        # 1. Salvar a resposta do usuário no banco de mensagens
        await self.database.save_message(
            conversation_id=conversation_id,
            role="user",
            content=user_response
        )

        # 2. Configurar o thread_id para o checkpointer
        config = {
            "configurable": {
                "thread_id": conversation_id,
                "llm": self.llm,
                "vector_store": self.vector_store,
                "reranker": self.reranker,
                "database": self.database
            }
        }

        # 3. Atualizar o estado do grafo no checkpoint com o esclarecimento
        await compiled_graph.aupdate_state(
            config,
            {"user_clarification": user_response},
            as_node="ask_user"
        )

        # 4. Retomar a execução em streaming passando None no input (lê do checkpoint)
        final_state = {}
        try:
            async for event in compiled_graph.astream_events(
                None,
                config=config,
                version="v2"
            ):
                event_type = event.get("event")
                node_name = event.get("metadata", {}).get("langgraph_node")

                # Emitir transição de nós
                if event_type == "on_node_start":
                    node = event.get("name")
                    msg = "Processando..."
                    if node == "orchestrator":
                        msg = "Orquestrador processando a clarificação do usuário..."
                    elif node == "researcher":
                        msg = "Pesquisando com base no novo contexto..."
                    elif node == "writer":
                        msg = "Redigindo resposta final esclarecida..."
                    elif node == "judge":
                        msg = "Judge validando resposta esclarecida..."
                    elif node == "recap":
                        msg = "Sintetizando resposta esclarecida..."

                    yield {
                        "event": "status",
                        "agent": node,
                        "message": msg
                    }

                # Streaming de tokens
                elif event_type == "on_chat_model_stream" and node_name == "writer":
                    chunk = event.get("data", {}).get("chunk")
                    text = ""
                    if hasattr(chunk, "text"):
                        text = chunk.text
                    elif isinstance(chunk, dict) and "text" in chunk:
                        text = chunk["text"]
                    elif hasattr(chunk, "content"):
                        text = chunk.content
                        
                    if text:
                        yield {
                            "event": "token",
                            "text": text
                        }

                # Obter estado final
                elif event_type == "on_chain_end" and event.get("name") == "LangGraph":
                    final_state = event.get("data", {}).get("output", {})

            # 5. Pós-processamento e persistência
            answer = final_state.get("answer", "")
            citations = final_state.get("citations") or []
            recap = final_state.get("recap", "")
            next_step = final_state.get("next_step")

            is_hil = next_step == "ask_user" or answer.startswith("PAUSE_HIL:")
            
            if not is_hil:
                # Salvar mensagem
                msg_id = await self.database.save_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=answer,
                    route=final_state.get("next_step", "RAG_CLARIFIED"),
                    token_count=len(answer.split())
                )
                
                # Salvar citações
                if citations:
                    await self.database.save_citations(msg_id, citations)
                
                # Incrementar cotas
                await self.database.increment_user_question_count(user_id)
            else:
                clean_question = answer.replace("PAUSE_HIL: ", "")
                await self.database.save_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=clean_question,
                    route="ASK_USER"
                )

            # Emitir resultado final
            yield {
                "event": "final",
                "answer": answer,
                "citations": [cit.model_dump() for cit in citations],
                "recap": recap,
                "conversation_id": conversation_id,
                "is_hil": is_hil
            }

        except Exception as e:
            logger.error(f"Erro ao retomar grafo na clarificação: {e}", exc_info=True)
            yield {
                "event": "error",
                "message": f"Erro interno na clarificação: {str(e)}"
            }
