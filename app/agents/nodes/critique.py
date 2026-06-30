from typing import Literal, Any
from pydantic import BaseModel, Field
from app.agents.state import GraphState, SessionCounters
from app.application.interfaces.llm_gateway import LLMGateway

class CritiqueVerdict(BaseModel):
    """Modelo de resposta estruturada para validação da pesquisa."""
    verdict: Literal["sufficient", "insufficient"] = Field(
        ..., description="Indica se os chunks recuperados contêm informação suficiente e relevante para responder à pergunta."
    )
    feedback: str = Field(
        ..., description="Detalhamento sobre o que falta ou por que os chunks atuais são insuficientes."
    )

from langchain_core.runnables import RunnableConfig

async def critique_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Nó Critique que valida se as informações recuperadas no RAG são suficientes."""
    llm: LLMGateway = config["configurable"]["llm"]
    query = state.get("query", "")
    research_results = state.get("research_results") or []
    counters = state.get("session_counters")

    # Agregar chunks para análise
    all_chunks = []
    for res in research_results:
        all_chunks.extend(res.get("chunks", []))

    # Se não retornou nenhum chunk, marcar direto como insuficiente
    if not all_chunks:
        return {
            "critique_verdict": "insufficient",
            "critique_feedback": "Nenhum resultado foi encontrado na busca vetorial no Qdrant."
        }

    # Prompt para a LLM avaliar relevância
    system_instruction = (
        "Você é o Critique do sistema Gnosis Chat. Sua tarefa é analisar se as fontes recuperadas (chunks) "
        "são suficientes, verídicas e relevantes para responder de forma completa à pergunta do usuário.\n"
        "Se os chunks contêm as respostas, decida por 'sufficient'. Se não respondem ou são completamente irrelevantes, "
        "decida por 'insufficient' e diga exatamente quais partes da pergunta ficaram sem resposta no feedback."
    )

    prompt = (
        f"Pergunta do Usuário: {query}\n\n"
        f"Textos Recuperados das Obras:\n"
        f"{chr(10).join(f'- {c}' for c in all_chunks[:15])}\n\n"
        "Avalie a qualidade das fontes em relação à pergunta do usuário."
    )

    verdict: CritiqueVerdict = await llm.generate_json(
        prompt=prompt,
        response_schema=CritiqueVerdict,
        system_instruction=system_instruction,
        temperature=0.1,
        use_premium_model=False # Lite
    )

    # Incrementar contador de loops de critique
    if counters:
        counters["critique_loops"] += 1

    return {
        "critique_verdict": verdict.verdict,
        "critique_feedback": verdict.feedback,
        "session_counters": counters
    }
