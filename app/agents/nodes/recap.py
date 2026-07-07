from typing import Any
from app.agents.state import GraphState
from app.application.interfaces.llm_gateway import LLMGateway

from langchain_core.runnables import RunnableConfig

async def recap_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Nó Recap que resume a resposta final em 2 ou 3 frases curtas e diretas."""
    from app.agents.nodes.utils import get_configurable_llm
    llm: LLMGateway = get_configurable_llm(config)
    answer = state.get("answer", "")

    if not answer:
        return {"recap": ""}

    system_instruction = (
        "Você é o Recap, um assistente cujo único objetivo é mapear e descrever de forma ultra-concisa a jornada "
        "lógica da resposta (o percurso de aprendizado). Em no máximo 2 frases curtas, sintetize o caminho percorrido "
        "(ex: 'Partimos de [Conceito A], exploramos [Tópico B] e concluímos com a relação sobre [Conceito C]')."
    )

    prompt = (
        f"Resposta Completa:\n{answer}\n\n"
        "Descreva a jornada lógica ou percurso de aprendizado da resposta acima em até 2 frases curtas."
    )

    recap = await llm.generate_text(
        prompt=prompt,
        system_instruction=system_instruction,
        temperature=0.3,
        use_premium_model=False # Lite
    )

    return {"recap": recap.strip()}
