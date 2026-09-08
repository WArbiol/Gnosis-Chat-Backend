import asyncio
import json
import logging
from typing import Any, Type, AsyncGenerator
from google import genai
from google.genai import types
from google.genai.errors import APIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from app.application.interfaces.llm_gateway import LLMGateway
from app.core.config import settings

logger = logging.getLogger(__name__)


def is_retryable_error(exception: Exception) -> bool:
    """Verifica se o erro é elegível para retry genérico com backoff (500, 502, 504)."""
    if isinstance(exception, APIError):
        # 503 e 429 são tratados pelo fallback imediato de modelo
        return exception.code in [500, 502, 504]
    return False


def is_overload_or_spike(exception: Exception) -> bool:
    """Identifica especificamente erros de sobrecarga (503), picos de tráfego, limite de cota (429) e timeouts de fila."""
    if isinstance(exception, (TimeoutError, asyncio.TimeoutError)):
        return True
    if isinstance(exception, APIError):
        return exception.code in [429, 502, 503, 504]
    err_str = str(exception).lower()
    return any(k in err_str for k in ["503", "429", "overloaded", "resource_exhausted", "unavailable", "spikes", "timeout"])


def is_embedding_retryable(exception: Exception) -> bool:
    """Retry para embeddings em caso de 429 (quota burst/rate limit) ou 503 temporários."""
    if isinstance(exception, APIError):
        return exception.code in [429, 500, 502, 503, 504]
    err_str = str(exception).lower()
    return any(k in err_str for k in ["429", "503", "resource_exhausted", "unavailable", "quota", "spikes"])


class GeminiLLM(LLMGateway):
    """Implementação simplificada e robusta do LLMGateway com cascata direta e timeouts saudáveis."""

    def __init__(self) -> None:
        self.client = genai.Client(api_key=settings.google_api_key)
        # Cascata direta e estável:
        # Primário (3.8) -> Fallback Estável (3.5) -> Fallback de Alta Disponibilidade (2.5)
        self.premium_models = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
        self.lite_models = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash"]

    @property
    def premium_model(self) -> str:
        return self.premium_models[0]

    @property
    def fallback_premium_model(self) -> str:
        return self.premium_models[1]

    @property
    def lite_model(self) -> str:
        return self.lite_models[0]

    @property
    def fallback_lite_model(self) -> str:
        return self.lite_models[1]

    async def _execute_generate_content(
        self,
        model: str,
        contents: Any,
        config: types.GenerateContentConfig,
        timeout: float = 25.0
    ) -> Any:
        try:
            return await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                ),
                timeout=timeout
            )
        except (asyncio.TimeoutError, TimeoutError):
            logger.warning(
                f"⏱️ [LLM Call Timeout] Modelo {model} não respondeu em {timeout:.0f}s. Disparando fallback..."
            )
            raise TimeoutError(f"Timeout de {timeout:.0f}s aguardando resposta do modelo {model}")

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        use_premium_model: bool = False
    ) -> str:
        models = self.premium_models if use_premium_model else self.lite_models
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction
        )

        last_error = None
        for i, model in enumerate(models):
            try:
                response = await self._execute_generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                    timeout=25.0
                )
                return response.text or ""
            except Exception as e:
                last_error = e
                if not is_overload_or_spike(e):
                    logger.error(f"Erro irrecuperável em generate_text com {model}: {e}")
                    raise e

                next_model = models[i + 1] if i + 1 < len(models) else None
                if next_model:
                    logger.warning(
                        f"⚠️ [LLM Fallback] Modelo {model} indisponível ({getattr(e, 'code', 'spikes/timeout')}). "
                        f"Tentando {next_model}..."
                    )

        if last_error:
            raise last_error
        return ""

    async def generate_text_stream(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        use_premium_model: bool = False
    ) -> AsyncGenerator[str, None]:
        models = self.premium_models if use_premium_model else self.lite_models
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction
        )

        last_error = None
        for i, model in enumerate(models):
            yielded_any = False
            try:
                response_stream = await self.client.aio.models.generate_content_stream(
                    model=model,
                    contents=prompt,
                    config=config
                )
                ait = response_stream.__aiter__()
                # Timeout de 35s para o primeiro chunk: acomoda prefill com folga em horários de pico
                try:
                    first_chunk = await asyncio.wait_for(ait.__anext__(), timeout=35.0)
                    if first_chunk.text:
                        yielded_any = True
                        yield first_chunk.text
                except StopAsyncIteration:
                    return
                except (asyncio.TimeoutError, TimeoutError):
                    logger.warning(
                        f"⏱️ [LLM Stream Timeout] Modelo {model} não enviou primeiro token em 35s. Acionando fallback..."
                    )
                    raise TimeoutError(f"Timeout de 35s aguardando primeiro token do modelo {model}")

                async for chunk in ait:
                    if chunk.text:
                        yielded_any = True
                        yield chunk.text
                return
            except Exception as e:
                last_error = e
                if yielded_any or not is_overload_or_spike(e):
                    logger.error(f"Erro irrecuperável no streaming com modelo {model}: {e}")
                    raise e

                next_model = models[i + 1] if i + 1 < len(models) else None
                if next_model:
                    logger.warning(
                        f"⚠️ [LLM Stream Fallback] Modelo {model} sobrecarregado ({getattr(e, 'code', 'spikes/timeout')}). "
                        f"Tentando {next_model} em tempo real..."
                    )

        if last_error:
            raise last_error

    async def generate_json(
        self,
        prompt: str,
        response_schema: Type[Any],
        system_instruction: str | None = None,
        temperature: float = 0.1,
        use_premium_model: bool = False
    ) -> Any:
        models = self.premium_models if use_premium_model else self.lite_models
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=response_schema
        )

        response = None
        last_error = None
        for i, model in enumerate(models):
            try:
                response = await self._execute_generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                    timeout=25.0
                )
                break
            except Exception as e:
                last_error = e
                if not is_overload_or_spike(e):
                    logger.error(f"Erro irrecuperável em generate_json com {model}: {e}")
                    raise e

                next_model = models[i + 1] if i + 1 < len(models) else None
                if next_model:
                    logger.warning(
                        f"⚠️ [LLM JSON Fallback] Modelo {model} indisponível ({getattr(e, 'code', 'spikes/timeout')}). "
                        f"Tentando {next_model}..."
                    )

        if response is None:
            if last_error:
                raise last_error
            raise RuntimeError("Nenhum modelo respondeu ao generate_json após fallback.")

        text_data = response.text or "{}"
        if hasattr(response_schema, "model_validate_json"):
            return response_schema.model_validate_json(text_data)

        return json.loads(text_data)

    @retry(
        retry=retry_if_exception(is_embedding_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.2, min=1.2, max=4),
        reraise=True
    )
    async def generate_embeddings(self, text: str) -> list[float]:
        response = await self.client.aio.models.embed_content(
            model="gemini-embedding-2-preview",
            contents=text
        )

        if response.embeddings:
            return response.embeddings[0].values
        return []
