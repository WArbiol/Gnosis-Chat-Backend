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
    refined_sub_queries: list[str] = Field(
        default=[], description="Se o veredito for 'insufficient', gere de 1 a 2 novas sub-queries ultra-focadas no que ficou faltando. IMPORTANTE: Use sinônimos técnicos e termos esotéricos legítimos encontrados nas próprias fontes lidas nos chunks atuais (ex: se o usuário perguntou sobre 'Morte do Ego' e as fontes citam 'Dissolução do Yo' ou 'Agregados Psíquicos', inclua esses termos exatos das obras nas novas sub-queries)."
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
            "critique_feedback": "Nenhum resultado foi encontrado na busca vetorial no Qdrant.",
            "sub_queries": [query]
        }

    # Prompt para a LLM avaliar relevância
    system_instruction = (
        "Você é o Critique do sistema Pergunte à Gnosis. Sua tarefa é analisar se as fontes recuperadas (chunks) "
        "são suficientes e relevantes para responder de forma completa à pergunta do usuário.\n"
        "Diretrizes:\n"
        "1. Se os chunks respondem de forma completa e satisfatória, defina o veredito como 'sufficient'.\n"
        "2. Se faltar alguma informação importante, defina o veredito como 'insufficient'. No campo 'feedback', aponte exatamente o que está faltando.\n"
        "3. SINÔNIMOS DOS AUTORES: Ao definir novas 'refined_sub_queries', observe atentamente a terminologia esotérica presente nos trechos já lidos. Se a pergunta usou um termo comum (ex: 'morte do ego'), mas as fontes dos autores usam termos mais específicos ou sinônimos autênticos do acervo (ex: 'dissolução dos agregados psíquicos', 'morte do Yo', 'trabalho sobre si mesmo'), utilize esses termos exatos das obras para formular as novas sub-queries da próxima busca."
    )

    prompt = (
        f"Pergunta do Usuário: {query}\n\n"
        f"Textos Recuperados das Obras:\n"
        f"{chr(10).join(f'- {c}' for c in all_chunks[:15])}\n\n"
        "Avalie a qualidade das fontes em relação à pergunta do usuário e gere o veredito."
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

    # Forçar encerramento do loop se já tivermos feito a 1ª tentativa + 2 retries (critique_loops > 2, total 3 buscas)
    final_verdict = verdict.verdict
    final_feedback = verdict.feedback
    if counters and counters["critique_loops"] > 2:
        final_verdict = "sufficient"
        final_feedback = "Limite de 2 tentativas extras (3 buscas no total) atingido. Prosseguindo com as fontes recuperadas."

    res_dict = {
        "critique_verdict": final_verdict,
        "critique_feedback": final_feedback,
        "session_counters": counters
    }

    # Se for insuficiente e o Critique gerou novas sub-queries, atualizamos o state para o Researcher
    if final_verdict == "insufficient" and verdict.refined_sub_queries:
        res_dict["sub_queries"] = verdict.refined_sub_queries

    return res_dict
