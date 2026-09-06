import pytest
from unittest.mock import MagicMock
from langchain_core.runnables import RunnableConfig
from app.agents.nodes.writer import writer_node
from app.schemas.chat import CitationDraft


@pytest.mark.asyncio
async def test_writer_round_robin_interleaving():
    """Garante que se existirem 3 sub-queries com 10 chunks cada,
    o Redator intercala os melhores de cada uma (Round-Robin) sem que a 1ª sub-query
    monopolize todas as vagas."""

    # Simular 3 sub-queries com chunks e citações diferentes
    sq1 = {
        "sub_query": "sq1",
        "chunks": [f"Chunk_SQ1_{i}" for i in range(10)],
        "citations": [CitationDraft(book_name="Livro A", author="Autor A", page=i, chamber=1, snippet="txt").model_dump() for i in range(10)]
    }
    sq2 = {
        "sub_query": "sq2",
        "chunks": [f"Chunk_SQ2_{i}" for i in range(10)],
        "citations": [CitationDraft(book_name="Livro B", author="Autor B", page=i, chamber=1, snippet="txt").model_dump() for i in range(10)]
    }
    sq3 = {
        "sub_query": "sq3",
        "chunks": [f"Chunk_SQ3_{i}" for i in range(10)],
        "citations": [CitationDraft(book_name="Livro C", author="Autor C", page=i, chamber=1, snippet="txt").model_dump() for i in range(10)]
    }

    state = {
        "query": "Explique A, B e C",
        "research_results": [sq1, sq2, sq3],
        "conversation_history": []
    }

    # Mock LLM que captura o prompt enviado ao Redator
    captured_prompt = []

    class MockStreamLLM:
        async def generate_text_stream(self, prompt, system_instruction=None, temperature=0.2, use_premium_model=False):
            captured_prompt.append(prompt)
            yield "Resposta gerada com sucesso."

    mock_llm = MockStreamLLM()
    config = RunnableConfig(configurable={"llm": mock_llm})

    from langchain_core.runnables import RunnableLambda
    result = await RunnableLambda(writer_node).ainvoke(state, config)

    prompt = captured_prompt[0]

    # Verifica que os TOP 1 de CADA sub-query estão presentes no prompt
    assert "Chunk_SQ1_0" in prompt
    assert "Chunk_SQ2_0" in prompt
    assert "Chunk_SQ3_0" in prompt

    # Verifica que os TOP 2 de CADA sub-query também estão presentes
    assert "Chunk_SQ1_1" in prompt
    assert "Chunk_SQ2_1" in prompt
    assert "Chunk_SQ3_1" in prompt

    # Verifica que os TOP 3 de CADA sub-query também estão presentes
    assert "Chunk_SQ1_2" in prompt
    assert "Chunk_SQ2_2" in prompt
    assert "Chunk_SQ3_2" in prompt

    # E o 10º chunk pertence a SQ1_3
    assert "Chunk_SQ1_3" in prompt

    # Chunks de menor relevância (>3) das sub-queries NÃO entraram (já que o teto é 10)
    assert "Chunk_SQ2_4" not in prompt
    assert "Chunk_SQ3_4" not in prompt
