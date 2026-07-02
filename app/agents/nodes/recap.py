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
        "Você é o Recap, um assistente cujo único objetivo é resumir respostas detalhadas em exatamente "
        "2 ou 3 frases diretas, impactantes e completas, que capturem a essência teológica da resposta."
    )

    prompt = (
        f"Resposta Completa:\n{answer}\n\n"
        "Gere o resumo de 2 a 3 frases."
    )

    recap = await llm.generate_text(
        prompt=prompt,
        system_instruction=system_instruction,
        temperature=0.3,
        use_premium_model=False # Lite
    )

    return {"recap": recap.strip()}
