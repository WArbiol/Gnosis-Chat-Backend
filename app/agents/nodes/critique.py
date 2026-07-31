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
    inferred_books: list[str] | None = Field(
        default=None, description="Se você identificou nos chunks atuais um livro específico onde a resposta continua ou está detalhada, informe o nome do livro."
    )
    inferred_page_start: int | None = Field(
        default=None, description="Se você identificou que a explicação continua nas páginas seguintes de um livro lido nos chunks, informe a página inicial para restringir o RAG."
    )
    inferred_page_end: int | None = Field(
        default=None, description="Página final para restringir a busca vetorial à faixa de páginas de interesse."
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

    # Prompt para a LLM avaliar relevância com sensibilidade e intuição analítica
    system_instruction = (
        "Você é um Pesquisador Gnóstico Sênior e analista de fontes literárias. Sua função é avaliar com intuição crítica "
        "se as fontes recuperadas (chunks) contêm substância suficiente e fiel para responder à pergunta do usuário.\n\n"
        "Sua postura analítica:\n"
        "- Se o material recuperado for rico e responder à dúvida de forma completa, defina o veredito como 'sufficient'.\n"
        "- Se faltar algo essencial para responder com profundidade, defina como 'insufficient' e use sua sensibilidade de pesquisador para direcionar a próxima busca. "
        "Sinta-se 100% livre para sugerir novas sub-queries usando a terminologia autêntica dos autores vista nos trechos já lidos (como sinônimos ou termos técnicos exatos das obras), "
        "ou indicar livros, autores e faixas de páginas específicas se notar que a explicação detalhada continua nas páginas seguintes de um livro."
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

    # Se for insuficiente e o Critique gerou novas sub-queries ou filtros de livro/páginas
    if final_verdict == "insufficient":
        if verdict.refined_sub_queries:
            res_dict["sub_queries"] = verdict.refined_sub_queries

        curr_filters = dict(state.get("metadata_filters") or {})
        if verdict.inferred_books:
            curr_filters["books"] = list(set((curr_filters.get("books") or []) + verdict.inferred_books))
        if verdict.inferred_page_start is not None:
            curr_filters["page_start"] = verdict.inferred_page_start
        if verdict.inferred_page_end is not None:
            curr_filters["page_end"] = verdict.inferred_page_end

        res_dict["metadata_filters"] = curr_filters

    return res_dict
