import asyncio
import os
import sys
import time
from dotenv import load_dotenv

# Carregar variáveis do .env do backend
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(backend_dir, ".env"))

sys.path.append(backend_dir)

from app.infrastructure.google.gemini_llm import GeminiLLM
from app.infrastructure.qdrant.qdrant_vector_store import QdrantVectorStore
from app.infrastructure.google.vertex_ranking import VertexRanking
from app.infrastructure.supabase.supabase_database import SupabaseDatabase
from app.agents.graph import compiled_graph
from app.schemas.user import UserProfile, PlanEnum

async def test():
    print("Inicializando componentes...")
    llm = GeminiLLM()
    vector_store = QdrantVectorStore()
    reranker = VertexRanking()
    database = SupabaseDatabase(None)
    
    # Criar estado inicial do grafo
    initial_state = {
        "query": "Quem é Lúcifer?",
        "user": UserProfile(
            id="test-user-123",
            email="test-user-123@gnosis.chat",
            plan=PlanEnum.BASIC,
            chamber_level=1,
            question_count=0
        ),
        "ui_filters": {},
        "conversation_history": [],
        "session_counters": {
            "researcher_calls": 0,
            "critique_loops": 0,
            "judge_loops": 0,
            "ask_user_calls": 0
        }
    }
    
    config = {
        "configurable": {
            "thread_id": "test-thread-id-12345",
            "llm": llm,
            "vector_store": vector_store,
            "reranker": reranker,
            "database": database
        }
    }
    
    print("\nExecutando o grafo em streaming...")
    try:
        async for event in compiled_graph.astream_events(
            initial_state,
            config=config,
            version="v2"
        ):
            event_type = event.get("event")
            name = event.get("name")
            print(f"Event: {event_type} | Name: {name}")
            
            # Se for token
            if event_type == "on_chat_model_stream":
                token = event.get("data", {}).get("chunk", {}).text
                if token:
                    print(token, end="", flush=True)
                    
    except Exception as e:
        print("\n\nOcorreu um erro na execução do grafo:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
