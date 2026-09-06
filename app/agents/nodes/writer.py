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

    # Limitar aos 5 chunks mais relevantes para garantir TTFT instantâneo e prefill leve
    MAX_WRITER_CHUNKS = 5
    chunks = chunks[:MAX_WRITER_CHUNKS]
    available_citations = available_citations[:MAX_WRITER_CHUNKS]

    # 2. Construir contexto para o redator
    context_str = ""
    for idx, (text, cit) in enumerate(zip(chunks, available_citations)):
        b_name = cit.get("book_name") if isinstance(cit, dict) else getattr(cit, "book_name", "Desconhecido")
        b_author = cit.get("author") if isinstance(cit, dict) else getattr(cit, "author", "Desconhecido")
        b_page = cit.get("page") if isinstance(cit, dict) else getattr(cit, "page", 1)
        b_chamber = cit.get("chamber") if isinstance(cit, dict) else getattr(cit, "chamber", 1)
        b_chapter = cit.get("chapter") if isinstance(cit, dict) else getattr(cit, "chapter", "N/A")
        context_str += (
            f"[Fonte #{idx + 1}]\n"
            f"Livro: {b_name}\n"
            f"Autor: {b_author}\n"
            f"Página: {b_page}\n"
            f"Câmara: {b_chamber}\n"
            f"Capítulo: {b_chapter or 'N/A'}\n"
            f"Texto: {text}\n\n"
        )

    system_instruction = (
        "Você é o Writer do sistema Pergunte à Gnosis. Sua tarefa é redigir uma resposta teológica e esotérica "
        "extremamente profunda, clara e fiel às fontes fornecidas. Não invente nenhuma informação.\n"
        "Regras estritas:\n"
        "1. Escreva em formato markdown limpo e elegante.\n"
        "2. Adicione referências explícitas no texto vinculadas às fontes usando o formato '[Livro, p. X]'.\n"
        "3. Não mencione números de fontes internas (ex: não escreva '[Fonte #1]'). Use apenas o nome do livro e página.\n"
        "4. Mantenha um tom respeitoso, solene e didático.\n"
        "5. IMPORTANTE: Distinga rigorosamente o título das obras de referência (metadados dos livros) dos conceitos, seres ou entidades teológicas descritos no conteúdo. Nunca confunda ou associe o nome/título de um livro (ex: 'Pistis Sophia Desvelada', 'O Divino Daimon', 'O Livro Amarelo') como se fosse o nome de uma divindade, processo ou entidade descrita nas fontes, a menos que o texto explicitamente fundamente essa relação. Trate os metadados bibliográficos estritamente como referências de catalogação.\n"
        "6. IDIOMA E GRAFIA: Se a pergunta for em português, responda obrigatoriamente em português do Brasil (pt-BR). Use grafias brasileiras legítimas (ex: escreva 'exata' e não 'exacta', 'fato' e não 'facto'). IMPORTANTE: Use sempre a palavra 'Gnosis' (com 'is' no final) em vez de 'Gnose'.\n"
        "7. SÍNTESE E SUGESTÕES: No final absoluto da sua resposta, adicione uma linha contendo exatamente '---RECAP---' seguida de 2 a 3 frases sintetizando a jornada de aprendizado da resposta. Em seguida, adicione uma linha contendo exatamente '---SUGESTOES---' e abaixo liste de 2 a 3 perguntas de continuação curtas e instigantes em pt-BR (uma por linha, iniciando com '- ')."
    )

    prompt = (
        f"Fontes de Referência:\n{context_str}\n"
        f"Histórico Recente da Conversa (Contexto auxiliar):\n{history}\n\n"
        f"Pergunta do Usuário: {query}\n\n"
        "Escreva a melhor resposta possível utilizando estritamente as fontes acima."
    )

    from langchain_core.callbacks.manager import adispatch_custom_event
    
    # Chamada com o modelo Premium (Gemini 3.0 Flash) em stream
    chunks_text = []
    async for token in llm.generate_text_stream(
        prompt=prompt,
        system_instruction=system_instruction,
        temperature=0.3,
        use_premium_model=True
    ):
        chunks_text.append(token)
        await adispatch_custom_event("writer_token", {"text": token})
        
    full_text = "".join(chunks_text)
    answer = full_text
    recap = ""
    suggested_followups = []

    if "---RECAP---" in full_text:
        parts = full_text.split("---RECAP---")
        answer = parts[0].strip()
        remainder = parts[1]
        if "---SUGESTOES---" in remainder:
            recap_part, sug_part = remainder.split("---SUGESTOES---")
            recap = recap_part.strip()
            for line in sug_part.strip().split("\n"):
                clean_line = line.strip().lstrip("-* ").strip()
                if clean_line:
                    suggested_followups.append(clean_line)
        else:
            recap = remainder.strip()
    elif "---SUGESTOES---" in full_text:
        parts = full_text.split("---SUGESTOES---")
        answer = parts[0].strip()
        sug_block = parts[1].strip()
        for line in sug_block.split("\n"):
            clean_line = line.strip().lstrip("-* ").strip()
            if clean_line:
                suggested_followups.append(clean_line)

    # 3. Mapear e retornar apenas as citações que foram de fato relevantes/fornecidas
    seen = set()
    final_citations = []
    for cit in available_citations:
        b_name = cit.get("book_name") if isinstance(cit, dict) else getattr(cit, "book_name", "Desconhecido")
        b_page = cit.get("page") if isinstance(cit, dict) else getattr(cit, "page", 1)
        key = (b_name, b_page)
        if key not in seen:
            seen.add(key)
            final_citations.append(cit)

    return {
        "answer": answer,
        "citations": final_citations,
        "recap": recap,
        "suggested_followups": suggested_followups
    }
