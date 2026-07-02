import asyncio
import os
import sys
from dotenv import load_dotenv

# Carregar variáveis do .env do backend
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(backend_dir, ".env"))

# Adicionar backend ao path
sys.path.append(backend_dir)

from app.infrastructure.google.gemini_llm import GeminiLLM
from app.agents.nodes.orchestrator import orchestrator_node, OrchestratorDecision
from app.schemas.user import UserProfile, PlanEnum

async def test():
    print("Inicializando GeminiLLM...")
    llm = GeminiLLM()
    
    # Criar um estado simulado
    state = {
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
            "llm": llm
        }
    }
    
    print("\nChamando orchestrator_node com a query: 'Quem é Lúcifer?'...")
    try:
        updates = await orchestrator_node(state, config)
        print("\nSucesso! Updates retornados:")
        print(updates)
    except Exception as e:
        print("\nOcorreu um erro no orchestrator_node:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
