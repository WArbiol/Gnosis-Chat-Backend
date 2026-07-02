from typing import Any
from app.agents.state import GraphState
from app.application.interfaces.llm_gateway import LLMGateway
from app.schemas.conversation import CitationResponse

from langchain_core.runnables import RunnableConfig

async def writer_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Nó Writer que redige a resposta detalhada de alta qualidade esotérica."""
    from app.agents.nodes.utils import get_configurable_llm
    llm: LLMGateway = get_configurable_llm(config)
    query = state.get("query", "")
    research_results = state.get("research_results") or []
    history = state.get("conversation_history") or []

    # 1. Agregar chunks e citações disponíveis
    chunks: list[str] = []
    available_citations: list[CitationResponse] = []
    
    for res in research_results:
        for text, cit in zip(res.get("chunks", []), res.get("citations", [])):
            if text not in chunks:
                chunks.append(text)
                available_citations.append(cit)

    # 2. Construir contexto para o redator
    context_str = ""
    for idx, (text, cit) in enumerate(zip(chunks, available_citations)):
        context_str += (
            f"[Fonte #{idx + 1}]\n"
            f"Livro: {cit.book_name}\n"
            f"Autor: {cit.author}\n"
            f"Página: {cit.page}\n"
            f"Câmara: {cit.chamber}\n"
            f"Capítulo: {cit.chapter or 'N/A'}\n"
            f"Texto: {text}\n\n"
        )

    system_instruction = (
        "Você é o Writer do sistema Gnosis Chat. Sua tarefa é redigir uma resposta teológica e esotérica "
        "extremamente profunda, clara e fiel às fontes fornecidas. Não invente nenhuma informação.\n"
        "Regras estritas:\n"
        "1. Escreva em formato markdown limpo e elegante.\n"
        "2. Adicione referências explícitas no texto vinculadas às fontes usando o formato '[Livro, p. X]'.\n"
        "3. Não mencione números de fontes internas (ex: não escreva '[Fonte #1]'). Use apenas o nome do livro e página.\n"
        "4. Mantenha um tom respeitoso, solene e didático."
    )

    prompt = (
        f"Histórico Recente:\n{history}\n\n"
        f"Fontes de Referência:\n{context_str}\n"
        f"Pergunta do Usuário: {query}\n\n"
        "Escreva a melhor resposta possível utilizando estritamente as fontes acima."
    )

    # Chamada com o modelo Premium (Gemini 3.0 Flash)
    answer = await llm.generate_text(
        prompt=prompt,
        system_instruction=system_instruction,
        temperature=0.3,
        use_premium_model=True # Premium (Flash 3.0)
    )

    # 3. Mapear e retornar apenas as citações que foram de fato relevantes/fornecidas
    # Filtramos duplicados nas citações
    seen = set()
    final_citations = []
    for cit in available_citations:
        key = (cit.book_name, cit.page)
        if key not in seen:
            seen.add(key)
            final_citations.append(cit)

    return {
        "answer": answer,
        "citations": final_citations
    }
