import asyncio
import os
import sys
import time
from dotenv import load_dotenv

# Carregar variáveis do .env do backend
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(backend_dir, ".env"))

# Adicionar backend ao path
sys.path.append(backend_dir)

from app.infrastructure.google.gemini_llm import GeminiLLM
from app.infrastructure.qdrant.qdrant_vector_store import QdrantVectorStore
from app.infrastructure.google.vertex_ranking import VertexRanking
from app.agents.nodes.researcher import researcher_node
from app.schemas.user import UserProfile, PlanEnum

async def test():
    print("Inicializando adaptadores...")
    t0 = time.time()
    llm = GeminiLLM()
    print(f"GeminiLLM inicializado em {time.time() - t0:.2f}s")
    
    t0 = time.time()
    vector_store = QdrantVectorStore()
    print(f"QdrantVectorStore inicializado em {time.time() - t0:.2f}s")
    
    t0 = time.time()
    reranker = VertexRanking()
    print(f"VertexRanking inicializado em {time.time() - t0:.2f}s (has_auth={reranker.has_auth}, project_id={reranker.project_id})")

    # Estado simulado após orquestrador decidir 'researcher'
    state = {
        "query": "Quem é Lúcifer?",
        "sub_queries": ["Quem é Lúcifer?"],
        "metadata_filters": {"chamber_levels": [1]},
        "session_counters": {
            "researcher_calls": 0,
            "critique_loops": 0,
            "judge_loops": 0,
            "ask_user_calls": 0
        }
    }
    
    config = {
        "configurable": {
            "llm": llm,
            "vector_store": vector_store,
            "reranker": reranker
        }
    }
    
    print("\nExecutando researcher_node...")
    t0 = time.time()
    try:
        updates = await researcher_node(state, config)
        print(f"\nSucesso! Executado em {time.time() - t0:.2f}s")
        # Mostrar contagem de resultados
        results = updates.get("research_results", [])
        print(f"Número de queries executadas: {len(results)}")
        for r in results:
            print(f"Sub-query: {r['sub_query']}")
            print(f"Chunks retornados: {len(r['chunks'])}")
            if r['chunks']:
                print(f"Primeiro chunk (truncado): {r['chunks'][0][:200]}...")
    except Exception as e:
        print(f"\nErro no researcher_node após {time.time() - t0:.2f}s:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
