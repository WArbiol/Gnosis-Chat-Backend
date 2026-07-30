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
    from app.agents.nodes.utils import get_configurable_llm
    llm: LLMGateway = get_configurable_llm(config)
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
        "Você é o Critique do sistema Pergunte à Gnosis. Sua tarefa é analisar se as fontes recuperadas (chunks) "
        "são suficientes e relevantes para responder de forma completa à pergunta do usuário.\n"
        "Diretrizes:\n"
        "1. Se os chunks respondem de forma completa e satisfatória, defina o veredito como 'sufficient'.\n"
        "2. Se faltar alguma informação importante, defina o veredito como 'insufficient'. Ao invés de apenas classificar de forma genérica, você deve retornar de forma detalhada e construtiva no campo 'feedback' o que já foi encontrado de importante nas fontes atuais E apontar exatamente o que ainda está faltando para responder à pergunta.\n"
        "3. Se você souber ou suspeitar de pistas adicionais que ajudem no refino (como livros, autores, capítulos, termos de busca mais específicos ou até intervalos de páginas específicas), cite-os no feedback. Se não houver pistas concretas, descreva apenas conceitualmente o que falta. Lembre ao Orquestrador que ele pode aplicar qualquer um desses filtros, inclusive restringir a busca a uma página ou intervalo de páginas se você sugerir (pois o banco possui o campo 'page').\n"
        "4. Se os textos recuperados revelarem que o termo pesquisado possui múltiplos significados ou aplicações distintas nas obras, mencione essa diversidade no feedback para que o Orquestrador possa considerar se é o caso de solicitar esclarecimento ao usuário."
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

    # Forçar encerramento do loop se o limite (1 retry) for atingido para evitar gasto excessivo
    final_verdict = verdict.verdict
    final_feedback = verdict.feedback
    if counters and counters["critique_loops"] >= 1:
        final_verdict = "sufficient"
        final_feedback = "Limite de 1 tentativa extra atingido. Prosseguindo com as fontes recuperadas."

    return {
        "critique_verdict": final_verdict,
        "critique_feedback": final_feedback,
        "session_counters": counters
    }
