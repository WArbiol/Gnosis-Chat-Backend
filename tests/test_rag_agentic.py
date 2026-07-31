import pytest
from typing import Any, Type
from unittest.mock import AsyncMock

from app.domain.exceptions import QuotaExceededException
from app.schemas.user import UserProfile, PlanEnum
from app.schemas.chat import UIFilters, CitationDraft
from app.application.interfaces.llm_gateway import LLMGateway
from app.application.interfaces.vector_store_gateway import VectorStoreGateway, ChunkResult
from app.application.interfaces.reranker_gateway import RerankerGateway
from app.application.interfaces.database_gateway import DatabaseGateway

# Elementos sob teste
from app.agents.graph import compiled_graph
from app.application.use_cases.ask_rag_use_case import AskRagUseCase
from app.application.use_cases.clarify_use_case import ClarifyUseCase
from app.agents.nodes.orchestrator import OrchestratorDecision
from app.agents.nodes.critique import CritiqueVerdict
from app.agents.nodes.judge import JudgeVerdict

# --- MOCKS DOS GATEWAYS ---

class MockLLM(LLMGateway):
    def __init__(self):
        self.text_responses = {}
        self.json_responses = {}
        
    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        use_premium_model: bool = False
    ) -> str:
        # Ordenar chaves pelo tamanho decrescente para dar match no mais específico
        for key, val in sorted(self.text_responses.items(), key=lambda x: len(x[0]), reverse=True):
            if key in prompt:
                return val
        return "Resposta mock padrão."

    async def generate_text_stream(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        use_premium_model: bool = False
    ):
        text = await self.generate_text(prompt, system_instruction, temperature, use_premium_model)
        for chunk in text.split(" "):
            yield chunk + " "

    async def generate_json(
        self,
        prompt: str,
        response_schema: Type[Any],
        system_instruction: str | None = None,
        temperature: float = 0.1,
        use_premium_model: bool = False
    ) -> Any:
        # Se for decisão do orquestrador
        if response_schema == OrchestratorDecision:
            # Se for o teste de RAG (que pesquisa), na segunda chamada ele deve ir para o writer
            if "pergunta-rag" in prompt:
                if not hasattr(self, "rag_calls"):
                    self.rag_calls = 0
                self.rag_calls += 1
                if self.rag_calls > 1:
                    return OrchestratorDecision(thought="mock", next_step="writer")
                return OrchestratorDecision(thought="mock", next_step="researcher", sub_queries=["o que é a Essência?"])

            # Match inteligente baseado nas chaves configuradas do tipo OrchestratorDecision
            for key, val in sorted(self.json_responses.items(), key=lambda x: len(x[0]), reverse=True):
                if isinstance(val, OrchestratorDecision) and key.lower() in prompt.lower():
                    return val
            return OrchestratorDecision(thought="mock", next_step="direct_response", direct_answer="Olá gnóstico!")
            
        # Se for veredito do critique
        if response_schema == CritiqueVerdict:
            for key, val in sorted(self.json_responses.items(), key=lambda x: len(x[0]), reverse=True):
                if isinstance(val, CritiqueVerdict) and key.lower() in prompt.lower():
                    return val
            return CritiqueVerdict(verdict="sufficient", feedback="Tudo ok.")
            
        # Se for veredito do judge
        if response_schema == JudgeVerdict:
            for key, val in sorted(self.json_responses.items(), key=lambda x: len(x[0]), reverse=True):
                if isinstance(val, JudgeVerdict) and key.lower() in prompt.lower():
                    return val
            return JudgeVerdict(verdict="approved", feedback="Excelente resposta.")
            
        return {}

    async def generate_embeddings(self, text: str) -> list[float]:
        return [0.1] * 768


class MockVectorStore(VectorStoreGateway):
    def __init__(self):
        self.chunks = []
        self.last_search_args = {}
        
    async def search_books(
        self,
        query_vector: list[float],
        limit: int = 30,
        books: list[str] | None = None,
        authors: list[str] | None = None,
        chamber_levels: list[int] | None = None,
        chapters: list[str] | None = None,
        page_start: int | None = None,
        page_end: int | None = None
    ) -> list[ChunkResult]:
        self.last_search_args = {
            "books": books,
            "authors": authors,
            "chamber_levels": chamber_levels,
            "chapters": chapters,
            "page_start": page_start,
            "page_end": page_end
        }
        return self.chunks

    async def search_user_interests(self, user_id: str, query_vector: list[float], limit: int = 5) -> list[ChunkResult]:
        return []

    async def upsert_user_interest(self, user_id: str, interest_text: str, vector: list[float]) -> None:
        pass


class MockReranker(RerankerGateway):
    async def rerank(self, query: str, documents: list[ChunkResult], top_n: int = 10) -> list[ChunkResult]:
        return documents[:top_n]


class MockDatabase(DatabaseGateway):
    def __init__(self, user_profile: UserProfile, recent_messages_count: int = 0):
        self.profile = user_profile
        self.recent_count = recent_messages_count
        self.messages_saved = []
        self.citations_saved = []
        self.question_count_incremented = False

    async def get_user_profile(self, user_id: str) -> UserProfile:
        return self.profile

    async def increment_user_question_count(self, user_id: str) -> None:
        self.question_count_incremented = True

    async def count_user_messages_in_last_7_days(self, user_id: str) -> int:
        return self.recent_count

    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        route: str | None = None,
        token_count: int | None = None,
        suggested_followups: list[str] | None = None
    ) -> str:
        self.messages_saved.append({"role": role, "content": content, "route": route, "suggested_followups": suggested_followups})
        return "msg-id-123"

    async def save_citations(self, message_id: str, citations: list[CitationDraft]) -> None:
        self.citations_saved.extend(citations)

    async def get_recent_messages(self, conversation_id: str, limit: int = 10) -> list[dict[str, str]]:
        return []

    async def get_second_chamber_catalog(self) -> list[str]:
        return []


# --- CASOS DE TESTES ---

@pytest.mark.asyncio
async def test_direct_response_flow():
    """Valida se o fluxo de resposta direta funciona sem chamar o Researcher."""
    llm = MockLLM()
    vector_store = MockVectorStore()
    reranker = MockReranker()
    db = MockDatabase(
        UserProfile(id="123", email="user@test.com", plan=PlanEnum.FREE, chamber_level=1, question_count=0)
    )

    # Configurar decisão do Orquestrador
    llm.json_responses["Olá"] = OrchestratorDecision(
        thought="mock",
        next_step="direct_response",
        direct_answer="Saudações Gnósticas! Como posso ajudar?"
    )

    use_case = AskRagUseCase(llm, vector_store, reranker, db)
    
    events = []
    async for event in use_case.execute(
        query="Olá",
        user_id="123",
        ui_filters=UIFilters(),
        user_profile=db.profile,
        conversation_id="conv-1"
    ):
        events.append(event)

    # Verificar se executou com sucesso
    assert len(events) > 0
    final_event = events[-1]
    assert final_event["event"] == "final"
    assert final_event["answer"] == "Saudações Gnósticas! Como posso ajudar?"
    assert final_event["is_hil"] is False
    assert db.question_count_incremented is True


@pytest.mark.asyncio
async def test_quota_exceeded_free_user():
    """Valida se o limite de cotas do plano gratuito (3 mensagens/semana) bloqueia o uso."""
    llm = MockLLM()
    vector_store = MockVectorStore()
    reranker = MockReranker()
    # Mockando que o usuário já enviou 3 mensagens
    db = MockDatabase(
        UserProfile(id="123", email="user@test.com", plan=PlanEnum.FREE, chamber_level=1, question_count=3)
    )

    use_case = AskRagUseCase(llm, vector_store, reranker, db)

    with pytest.raises(QuotaExceededException) as exc_info:
        async for _ in use_case.execute(
            query="Fale sobre o Absoluto",
            user_id="123",
            ui_filters=UIFilters(),
            user_profile=db.profile
        ):
            pass

    assert "limite de 3 perguntas do plano Gratuito" in str(exc_info.value)


@pytest.mark.asyncio
async def test_rag_retrieval_flow():
    """Valida o fluxo completo de RAG contendo pesquisa, crítica, escrita e julgamento."""
    llm = MockLLM()
    vector_store = MockVectorStore()
    reranker = MockReranker()
    db = MockDatabase(
        UserProfile(id="123", email="user@test.com", plan=PlanEnum.BASIC, chamber_level=1, question_count=0)
    )

    # 1. Configurar decisão de rota do orquestrador
    llm.json_responses["pergunta-rag"] = OrchestratorDecision(
        thought="mock",
        next_step="researcher",
        sub_queries=["o que é a Essência?"]
    )
    
    # 2. Configurar resposta textual do redator
    llm.text_responses["Essência"] = "A Essência é a faísca divina no homem."

    # 3. Adicionar chunks de referência no banco vetorial
    vector_store.chunks = [
        {
            "text": "A Essência é o embrião da Alma.",
            "book_name": "A Caridade Universal",
            "author": "Samael Aun Weor",
            "page": 8,
            "chamber": 1,
            "chapter": "CAPÍTULO III",
            "score": 0.95
        }
    ]

    use_case = AskRagUseCase(llm, vector_store, reranker, db)
    
    events = []
    async for event in use_case.execute(
        query="pergunta-rag",
        user_id="123",
        ui_filters=UIFilters(),
        user_profile=db.profile,
        conversation_id="conv-2"
    ):
        events.append(event)

    final_event = events[-1]
    assert final_event["event"] == "final"
    assert "faísca divina" in final_event["answer"]
    assert len(final_event["citations"]) == 1
    assert final_event["citations"][0]["book_name"] == "A Caridade Universal"
    assert db.question_count_incremented is True


@pytest.mark.asyncio
async def test_human_in_the_loop_clarify_flow():
    """Valida a pausa HIL (Ask User) e a retomada com a clarificação do usuário."""
    llm = MockLLM()
    vector_store = MockVectorStore()
    reranker = MockReranker()
    db = MockDatabase(
        UserProfile(id="123", email="user@test.com", plan=PlanEnum.BASIC, chamber_level=1, question_count=0)
    )

    # 1. Orquestrador decide pedir esclarecimento
    llm.json_responses["pergunta-vaga"] = OrchestratorDecision(
        thought="mock",
        next_step="ask_user",
        clarification_question="Você está se referindo ao Absoluto ou ao Demiurgo?"
    )

    use_case = AskRagUseCase(llm, vector_store, reranker, db)
    
    events = []
    async for event in use_case.execute(
        query="pergunta-vaga",
        user_id="123",
        ui_filters=UIFilters(),
        user_profile=db.profile,
        conversation_id="conv-hil"
    ):
        events.append(event)

    final_event = events[-1]
    assert final_event["is_hil"] is True
    assert "Você está se referindo ao" in final_event["answer"]
    # Não deve incrementar cota na pergunta de HIL
    assert db.question_count_incremented is False

    # --- RETOMADA DO GRAFO (Clarify) ---
    
    # Orquestrador agora muda decisão para direct_response ao receber a clarificação
    llm.json_responses["Nota de esclarecimento"] = OrchestratorDecision(
        thought="mock",
        next_step="direct_response",
        direct_answer="Excelente. O Absoluto é o espaço abstrato incondicionado."
    )

    clarify_use_case = ClarifyUseCase(llm, vector_store, reranker, db)
    
    clarify_events = []
    async for event in clarify_use_case.execute(
        conversation_id="conv-hil",
        user_response="Me refiro ao Absoluto.",
        user_id="123"
    ):
        clarify_events.append(event)

    final_clarify_event = clarify_events[-1]
    assert final_clarify_event["is_hil"] is False
    assert "O Absoluto é o espaço" in final_clarify_event["answer"]
    assert db.question_count_incremented is True


@pytest.mark.asyncio
async def test_rag_page_filtering_flow():
    """Valida se filtros de páginas passados via UIFilters chegam ao Vector Store."""
    llm = MockLLM()
    vector_store = MockVectorStore()
    reranker = MockReranker()
    db = MockDatabase(
        UserProfile(id="123", email="user@test.com", plan=PlanEnum.BASIC, chamber_level=1, question_count=0)
    )

    # Configurar decisão de rota do orquestrador
    llm.json_responses["pergunta-rag-paginas"] = OrchestratorDecision(
        thought="mock",
        next_step="researcher",
        sub_queries=["o que é a Essência?"]
    )
    
    llm.text_responses["Essência"] = "A Essência é a faísca divina no homem."

    vector_store.chunks = [
        {
            "text": "A Essência é o embrião da Alma.",
            "book_name": "A Caridade Universal",
            "author": "Samael Aun Weor",
            "page": 15,
            "chamber": 1,
            "chapter": "CAPÍTULO III",
            "score": 0.95
        }
    ]

    use_case = AskRagUseCase(llm, vector_store, reranker, db)
    
    events = []
    ui_filters = UIFilters(page_start=10, page_end=20)
    async for event in use_case.execute(
        query="pergunta-rag-paginas",
        user_id="123",
        ui_filters=ui_filters,
        user_profile=db.profile,
        conversation_id="conv-paginas"
    ):
        events.append(event)

    # Verificar se os filtros de página foram passados para o Vector Store
    assert vector_store.last_search_args.get("page_start") == 10
    assert vector_store.last_search_args.get("page_end") == 20


@pytest.mark.asyncio
async def test_ask_rag_disconnect_preserves_background_task():
    """Garante que a desconexão do cliente HTTP (CancelledError no gerador) não aborta o salvamento em background."""
    import asyncio
    llm = MockLLM()
    vector_store = MockVectorStore()
    reranker = MockReranker()
    db = MockDatabase(
        UserProfile(id="123", email="user@test.com", plan=PlanEnum.BASIC, chamber_level=1, question_count=0)
    )

    llm.json_responses["pergunta-disconnect"] = OrchestratorDecision(
        thought="mock disconnect",
        next_step="researcher",
        sub_queries=["o que é o Ego?"]
    )
    llm.text_responses["Ego"] = "O Ego deve ser dissolvido."

    use_case = AskRagUseCase(llm, vector_store, reranker, db)

    gen = use_case.execute(
        query="pergunta-disconnect",
        user_id="123",
        ui_filters=None,
        user_profile=db.profile,
        conversation_id="conv-disconnect"
    )

    # 1. Consumir apenas o primeiro evento
    await anext(gen)

    # 2. Simular cancelamento do gerador (cliente desconectou do streaming HTTP)
    await gen.aclose()

    # 3. Aguardar brevemente para que o background task termine de rodar
    await asyncio.sleep(0.5)

    # 4. Verificar se a mensagem do assistente foi salva no banco apesar da desconexão
    assistant_msgs = [m for m in db.messages_saved if m["role"] == "assistant"]
    assert len(assistant_msgs) == 1


@pytest.mark.asyncio
async def test_critique_allows_up_to_two_retries_before_forcing_sufficient():
    """Garante que o nó Critique permite até 2 tentativas extras (3 no total) quando os resultados são insuficientes, e na 3ª tentativa força o prosseguimento."""
    from app.agents.nodes.critique import critique_node
    from langchain_core.runnables import RunnableConfig

    llm = MockLLM()
    # Mock do veredito 'insufficient'
    llm.json_responses["Avalie a qualidade"] = CritiqueVerdict(
        verdict="insufficient",
        feedback="Trechos insuficientes para responder."
    )

    config = RunnableConfig(configurable={"llm_gateway": llm})

    # --- Turno 1 (Primeira Busca): critique_loops = 0 ---
    state_turn1 = {
        "query": "pergunta-insuficiente",
        "research_results": [{"sub_query": "q1", "chunks": ["chunk 1"], "citations": [], "relevance_scores": [0.5]}],
        "session_counters": {"researcher_calls": 1, "critique_loops": 0, "judge_loops": 0, "ask_user_calls": 0}
    }

    res_turn1 = await critique_node(state_turn1, config)
    assert res_turn1["critique_verdict"] == "insufficient"
    assert res_turn1["session_counters"]["critique_loops"] == 1

    # --- Turno 2 (2ª Busca / 1º Retry): critique_loops = 1 ---
    state_turn2 = {
        "query": "pergunta-insuficiente",
        "research_results": [{"sub_query": "q2", "chunks": ["chunk 2"], "citations": [], "relevance_scores": [0.5]}],
        "session_counters": res_turn1["session_counters"]
    }

    res_turn2 = await critique_node(state_turn2, config)
    assert res_turn2["critique_verdict"] == "insufficient"
    assert res_turn2["session_counters"]["critique_loops"] == 2

    # --- Turno 3 (3ª Busca / 2º Retry): critique_loops = 2 ---
    state_turn3 = {
        "query": "pergunta-insuficiente",
        "research_results": [{"sub_query": "q3", "chunks": ["chunk 3"], "citations": [], "relevance_scores": [0.5]}],
        "session_counters": res_turn2["session_counters"]
    }

    res_turn3 = await critique_node(state_turn3, config)
    assert res_turn3["critique_verdict"] == "sufficient"
    assert "Limite de 2 tentativas extras (3 buscas no total) atingido" in res_turn3["critique_feedback"]
    assert res_turn3["session_counters"]["critique_loops"] == 3



