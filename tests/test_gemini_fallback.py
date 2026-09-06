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
    resp_mock.text = "Resposta vinda do fallback 3.6"

    mock_generate = AsyncMock()
    # 1ª tentativa com 3.8 falha com 503, 2ª chamada (com fallback 3.6) tem sucesso
    mock_generate.side_effect = [err_503, resp_mock]

    llm.client.aio.models.generate_content = mock_generate

    result = await llm.generate_text(
        prompt="Pergunta teológica profunda",
        use_premium_model=True
    )

    assert result == "Resposta vinda do fallback 3.6"
    assert mock_generate.call_count == 2
    # Primeira chamada foi para 3.8
    assert mock_generate.call_args_list[0].kwargs["model"] == "gemini-3.8-flash"
    # Segunda chamada foi para 3.6
    assert mock_generate.call_args_list[1].kwargs["model"] == "gemini-3.6-flash"


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
    # 1ª tentativa com 3.8 falha com 503, 2ª chamada (fallback 3.6) retorna o stream
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
    assert mock_stream_call.call_args_list[1].kwargs["model"] == "gemini-3.6-flash"


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
    assert mock_generate.call_args_list[1].kwargs["model"] == "gemini-3.6-flash"


@pytest.mark.asyncio
async def test_generate_text_stream_double_fallback_on_503():
    """Garante que se tanto 3.8 quanto 3.6 estiverem em pico (503), o sistema cai transparentemente no 3.5-flash."""
    llm = GeminiLLM()

    err_503 = APIError(503, {"error": {"message": "Model overloaded high spikes"}})

    class MockStream:
        async def __aiter__(self):
            for chunk_text in ["Resposta ", "do 3.5"]:
                chunk = MagicMock()
                chunk.text = chunk_text
                yield chunk

    mock_stream_call = AsyncMock()
    # 1ª tentativa 3.8 falha com 503, 2ª tentativa 3.6 falha com 503, 3ª tentativa (3.5) tem sucesso
    mock_stream_call.side_effect = [err_503, err_503, MockStream()]

    llm.client.aio.models.generate_content_stream = mock_stream_call

    collected = []
    async for chunk in llm.generate_text_stream(
        prompt="Pergunta em streaming crítico",
        use_premium_model=True
    ):
        collected.append(chunk)

    assert "".join(collected) == "Resposta do 3.5"
    assert mock_stream_call.call_count == 3
    assert mock_stream_call.call_args_list[0].kwargs["model"] == "gemini-3.8-flash"
    assert mock_stream_call.call_args_list[1].kwargs["model"] == "gemini-3.6-flash"
    assert mock_stream_call.call_args_list[2].kwargs["model"] == "gemini-3.5-flash"


@pytest.mark.asyncio
async def test_generate_json_fallback_on_timeout():
    """Garante que se um modelo travar além do timeout (7s), o fallback aciona imediatamente."""
    llm = GeminiLLM()

    resp_mock = MagicMock()
    resp_mock.text = '{"summary": "Sucesso após timeout"}'

    # 1ª tentativa demora e sofre TimeoutError, 2ª tentativa responde com sucesso
    mock_generate = AsyncMock()
    mock_generate.side_effect = [TimeoutError("Timeout de 7s"), resp_mock]
    llm.client.aio.models.generate_content = mock_generate

    result = await llm.generate_json(
        prompt="Extrair resumo",
        response_schema=SampleSchema,
        use_premium_model=True
    )

    assert isinstance(result, SampleSchema)
    assert result.summary == "Sucesso após timeout"
    assert mock_generate.call_count == 2
    assert mock_generate.call_args_list[0].kwargs["model"] == "gemini-3.8-flash"
    assert mock_generate.call_args_list[1].kwargs["model"] == "gemini-3.6-flash"


@pytest.mark.asyncio
async def test_generate_embeddings_retry_on_429():
    """Garante que erro 429 de quota/burst no embed_content seja retentado com sucesso."""
    llm = GeminiLLM()

    err_429 = APIError(429, {"error": {"message": "Resource exhausted"}})
    mock_success = MagicMock()
    mock_emb = MagicMock()
    mock_emb.values = [0.1, 0.2, 0.3]
    mock_success.embeddings = [mock_emb]

    mock_embed = AsyncMock(side_effect=[err_429, mock_success])
    llm.client.aio.models.embed_content = mock_embed

    result = await llm.generate_embeddings("texto para vetor")

    assert result == [0.1, 0.2, 0.3]
    assert mock_embed.call_count == 2


