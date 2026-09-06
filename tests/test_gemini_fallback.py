import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import BaseModel
from google.genai.errors import APIError
from app.infrastructure.google.gemini_llm import GeminiLLM


class SampleSchema(BaseModel):
    summary: str


@pytest.mark.asyncio
async def test_generate_text_fallback_on_503():
    llm = GeminiLLM()

    # Mock APIError 503
    err_503 = APIError(503, {"error": {"message": "Model overloaded high spikes"}})

    resp_mock = MagicMock()
    resp_mock.text = "Resposta vinda do fallback 3.7"

    mock_generate = AsyncMock()
    # 1ª tentativa com 3.8 falha com 503, 2ª chamada (com fallback 3.7) tem sucesso
    mock_generate.side_effect = [err_503, resp_mock]

    llm.client.aio.models.generate_content = mock_generate

    result = await llm.generate_text(
        prompt="Pergunta teológica profunda",
        use_premium_model=True
    )

    assert result == "Resposta vinda do fallback 3.7"
    assert mock_generate.call_count == 2
    # Primeira chamada foi para 3.8
    assert mock_generate.call_args_list[0].kwargs["model"] == "gemini-3.8-flash"
    # Segunda chamada foi para 3.7
    assert mock_generate.call_args_list[1].kwargs["model"] == "gemini-3.7-flash"


@pytest.mark.asyncio
async def test_generate_text_stream_fallback_on_503():
    llm = GeminiLLM()

    err_503 = APIError(503, {"error": {"message": "Model overloaded high spikes"}})

    # Chunk stream mock para o fallback
    class MockStream:
        async def __aiter__(self):
            for chunk_text in ["Chunk 1 ", "Chunk 2"]:
                chunk = MagicMock()
                chunk.text = chunk_text
                yield chunk

    mock_stream_call = AsyncMock()
    # 1ª tentativa com 3.8 falha com 503, 2ª chamada (fallback 3.7) retorna o stream
    mock_stream_call.side_effect = [err_503, MockStream()]

    llm.client.aio.models.generate_content_stream = mock_stream_call

    collected = []
    async for chunk in llm.generate_text_stream(
        prompt="Pergunta em streaming",
        use_premium_model=True
    ):
        collected.append(chunk)

    assert "".join(collected) == "Chunk 1 Chunk 2"
    assert mock_stream_call.call_count == 2
    assert mock_stream_call.call_args_list[0].kwargs["model"] == "gemini-3.8-flash"
    assert mock_stream_call.call_args_list[1].kwargs["model"] == "gemini-3.7-flash"


@pytest.mark.asyncio
async def test_generate_json_fallback_on_503():
    llm = GeminiLLM()

    err_503 = APIError(503, {"error": {"message": "The service is currently unavailable"}})

    resp_mock = MagicMock()
    resp_mock.text = '{"summary": "Sucesso no fallback JSON"}'

    mock_generate = AsyncMock()
    mock_generate.side_effect = [err_503, resp_mock]

    llm.client.aio.models.generate_content = mock_generate

    result = await llm.generate_json(
        prompt="Extrair resumo",
        response_schema=SampleSchema,
        use_premium_model=True
    )

    assert isinstance(result, SampleSchema)
    assert result.summary == "Sucesso no fallback JSON"
    assert mock_generate.call_count == 2
    assert mock_generate.call_args_list[0].kwargs["model"] == "gemini-3.8-flash"
    assert mock_generate.call_args_list[1].kwargs["model"] == "gemini-3.7-flash"
