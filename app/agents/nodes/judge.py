from typing import Literal, Any
from pydantic import BaseModel, Field
from app.agents.state import GraphState, SessionCounters
from app.application.interfaces.llm_gateway import LLMGateway

class JudgeVerdict(BaseModel):
    """Modelo de resposta estruturada para auditoria de alucinações."""
    verdict: Literal["approved", "rejected"] = Field(
        ..., description="Indica se a resposta está totalmente livre de alucinações e fiel às fontes fornecidas."
    )
    feedback: str = Field(
        ..., description="Análise detalhada sobre alucinações encontradas ou aprovação da resposta."
    )

from langchain_core.runnables import RunnableConfig

async def judge_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Nó Judge que audita a resposta do Writer contra alucinações."""
    llm: LLMGateway = config["configurable"]["llm"]
    answer = state.get("answer", "")
    research_results = state.get("research_results") or []
    counters = state.get("session_counters")

    # Agregar chunks originais
    all_chunks = []
    for res in research_results:
        all_chunks.extend(res.get("chunks", []))

    if not all_chunks:
        return {
            "judge_verdict": "approved",
            "judge_feedback": "Nenhuma fonte pesquisada. Pulando validação contra fontes."
        }

    # Prompt para auditar a fidelidade
    system_instruction = (
        "Você é o Judge do sistema Gnosis Chat. Sua única responsabilidade é realizar uma auditoria rígida "
        "contra alucinações na resposta gerada pelo Writer.\n"
        "Regras de Auditoria:\n"
        "1. Compare cada afirmação na resposta com as fontes originais fornecidas.\n"
        "2. Se a resposta contiver fatos, conceitos ou afirmações que não podem ser comprovados pelas fontes, "
        "ou se citar páginas inexistentes, rejeite ('rejected') imediatamente.\n"
        "3. Se a resposta for estritamente fiel e bem fundamentada, aprove ('approved')."
    )

    prompt = (
        f"Fontes Originais:\n{chr(10).join(f'- {c}' for c in all_chunks)}\n\n"
        f"Resposta do Writer:\n{answer}\n\n"
        "Realize a auditoria e dê o seu veredito detalhado."
    )

    verdict: JudgeVerdict = await llm.generate_json(
        prompt=prompt,
        response_schema=JudgeVerdict,
        system_instruction=system_instruction,
        temperature=0.1,
        use_premium_model=False # Lite
    )

    # Incrementar contador de loops de judge
    if counters:
        counters["judge_loops"] += 1

    # Limite rígido de loops de rejeição: se estourar, aprova por segurança para evitar timeout
    final_verdict = verdict.verdict
    if counters and counters["judge_loops"] >= 3:
        final_verdict = "approved"

    return {
        "judge_verdict": final_verdict,
        "judge_feedback": verdict.feedback,
        "session_counters": counters
    }
