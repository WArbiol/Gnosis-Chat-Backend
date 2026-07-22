from typing import Any
from pydantic import BaseModel, Field
from app.agents.state import GraphState
from app.application.interfaces.llm_gateway import LLMGateway
from langchain_core.runnables import RunnableConfig

class RecapOutput(BaseModel):
    recap: str = Field(
        ..., description="Síntese ultra-concisa de até 3 frases sobre a jornada lógica/percurso de aprendizado da resposta."
    )
    suggested_followups: list[str] = Field(
        ..., description="Lista com exatamente 2 ou 3 perguntas de continuação curtas, diretas e naturais em português do Brasil (pt-BR)."
    )

async def recap_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Nó Recap que sintetiza o percurso de aprendizado e sugere 2-3 perguntas de acompanhamento."""
    from app.agents.nodes.utils import get_configurable_llm
    llm: LLMGateway = get_configurable_llm(config)
    answer = state.get("answer", "")

    if not answer:
        return {"recap": "", "suggested_followups": []}

    system_instruction = (
        "Você é o Recap do sistema Gnosis Chat.\n"
        "Sua função é gerar dois elementos:\n"
        "1. 'recap': Sintetize em no máximo 3 frases curtas o percurso de aprendizado da resposta (ex: 'Partimos de [Conceito A], exploramos [Tópico B] e concluímos com [Conceito C]').\n"
        "2. 'suggested_followups': Gere 2 a 3 perguntas de continuação inteligentes, instigantes e curtas (máximo 10 palavras cada) que o usuário poderia fazer a seguir para aprofundar o estudo. Escreva em português do Brasil (pt-BR)."
    )

    prompt = (
        f"Resposta Completa:\n{answer}\n\n"
        "Gere a síntese do percurso de aprendizado ('recap') e as 2 a 3 perguntas de acompanhamento sugeridas ('suggested_followups')."
    )

    try:
        result: RecapOutput = await llm.generate_json(
            prompt=prompt,
            response_schema=RecapOutput,
            system_instruction=system_instruction,
            temperature=0.3,
            use_premium_model=False # Lite
        )
        return {
            "recap": result.recap.strip(),
            "suggested_followups": result.suggested_followups
        }
    except Exception as e:
        return {
            "recap": answer[:150],
            "suggested_followups": []
        }
