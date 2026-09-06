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
    """Identifica especificamente erros de sobrecarga (503), picos de tráfego e limite de cota (429)."""
    if isinstance(exception, APIError):
        return exception.code in [429, 502, 503, 504]
    err_str = str(exception).lower()
    return any(k in err_str for k in ["503", "429", "overloaded", "resource_exhausted", "unavailable", "spikes"])


class GeminiLLM(LLMGateway):
    """Implementação concreta do LLMGateway usando o SDK google-genai do Google com resiliência em cascata."""

    def __init__(self) -> None:
        self.client = genai.Client(api_key=settings.google_api_key)
        # Cascata de modelos: se o 3.8 falhar (503), tenta o 3.7. Se o 3.7 também estiver sobrecarregado, tenta o 2.5-flash estável.
        self.premium_models = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-2.5-flash"]
        self.lite_models = ["gemini-3.5-flash-lite", "gemini-2.5-flash"]

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

    @retry(
        retry=retry_if_exception(is_retryable_error),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=3),
        reraise=True
    )
    async def _execute_generate_content(
        self,
        model: str,
        contents: Any,
        config: types.GenerateContentConfig
    ) -> Any:
        return await self.client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config
        )

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

        for i, model in enumerate(models):
            try:
                response = await self._execute_generate_content(
                    model=model,
                    contents=prompt,
                    config=config
                )
                return response.text or ""
            except Exception as e:
                is_last = i == len(models) - 1
                if not is_overload_or_spike(e) or is_last:
                    logger.error(f"Erro em generate_text com {model}: {e}")
                    raise e

                next_model = models[i + 1]
                logger.warning(
                    f"⚠️ [LLM Fallback] Modelo {model} sobrecarregado ({getattr(e, 'code', '503/spikes')}). "
                    f"Ativando fallback imediato para {next_model}..."
                )

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

        for i, model in enumerate(models):
            yielded_any = False
            try:
                response_stream = await self.client.aio.models.generate_content_stream(
                    model=model,
                    contents=prompt,
                    config=config
                )
                async for chunk in response_stream:
                    if chunk.text:
                        yielded_any = True
                        yield chunk.text
                return
            except Exception as e:
                is_last = i == len(models) - 1
                if yielded_any or not is_overload_or_spike(e) or is_last:
                    logger.error(f"Erro no streaming com modelo {model}: {e}")
                    raise e

                next_model = models[i + 1]
                logger.warning(
                    f"⚠️ [LLM Stream Fallback] Modelo {model} sobrecarregado ({getattr(e, 'code', '503/spikes')}). "
                    f"Ativando fallback em tempo real para {next_model}..."
                )

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
        for i, model in enumerate(models):
            try:
                response = await self._execute_generate_content(
                    model=model,
                    contents=prompt,
                    config=config
                )
                break
            except Exception as e:
                is_last = i == len(models) - 1
                if not is_overload_or_spike(e) or is_last:
                    logger.error(f"Erro em generate_json com {model}: {e}")
                    raise e

                next_model = models[i + 1]
                logger.warning(
                    f"⚠️ [LLM JSON Fallback] Modelo {model} indisponível ({getattr(e, 'code', '503/spikes')}). "
                    f"Ativando fallback para {next_model}..."
                )

        text_data = response.text or "{}"
        if hasattr(response_schema, "model_validate_json"):
            return response_schema.model_validate_json(text_data)

        return json.loads(text_data)

    @retry(
        retry=retry_if_exception(is_retryable_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
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
