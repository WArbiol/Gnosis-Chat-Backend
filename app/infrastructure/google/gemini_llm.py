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
    """Implementação concreta do LLMGateway usando o SDK google-genai do Google com resiliência em cascata de duas rodadas."""

    def __init__(self) -> None:
        self.client = genai.Client(api_key=settings.google_api_key)
        # Cascata de modelos em múltiplas rodadas:
        # Se um modelo sofrer pico 503, tenta o próximo imediatamente.
        # Se todos sofrerem pico simultâneo no Google, aguarda 1.5s de alívio e tenta novamente.
        self.premium_models = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-2.5-flash"]
        self.lite_models = ["gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-3.7-flash"]

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
        import asyncio
        models = self.premium_models if use_premium_model else self.lite_models

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction
        )

        last_error = None
        for attempt_round in range(2):
            if attempt_round > 0:
                logger.warning("⏳ [LLM Fallback] Todos os modelos em pico no Google. Aguardando 1.5s para 2ª rodada...")
                await asyncio.sleep(1.5)

            for i, model in enumerate(models):
                try:
                    response = await self._execute_generate_content(
                        model=model,
                        contents=prompt,
                        config=config
                    )
                    return response.text or ""
                except Exception as e:
                    last_error = e
                    if not is_overload_or_spike(e):
                        logger.error(f"Erro irrecuperável em generate_text com {model}: {e}")
                        raise e

                    next_model = models[i + 1] if i + 1 < len(models) else models[0]
                    logger.warning(
                        f"⚠️ [LLM Fallback R{attempt_round + 1}] Modelo {model} sobrecarregado ({getattr(e, 'code', '503/spikes')}). "
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
        import asyncio
        models = self.premium_models if use_premium_model else self.lite_models

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction
        )

        last_error = None
        for attempt_round in range(2):
            if attempt_round > 0:
                logger.warning("⏳ [LLM Stream Fallback] Todos os modelos em pico no Google. Aguardando 1.5s para 2ª rodada...")
                await asyncio.sleep(1.5)

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
                    last_error = e
                    if yielded_any or not is_overload_or_spike(e):
                        logger.error(f"Erro irrecuperável no streaming com modelo {model}: {e}")
                        raise e

                    next_model = models[i + 1] if i + 1 < len(models) else models[0]
                    logger.warning(
                        f"⚠️ [LLM Stream Fallback R{attempt_round + 1}] Modelo {model} sobrecarregado ({getattr(e, 'code', '503/spikes')}). "
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
        import asyncio
        models = self.premium_models if use_premium_model else self.lite_models

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=response_schema
        )

        response = None
        last_error = None
        for attempt_round in range(2):
            if attempt_round > 0:
                logger.warning("⏳ [LLM JSON Fallback] Todos os modelos em pico no Google. Aguardando 1.5s para 2ª rodada...")
                await asyncio.sleep(1.5)

            for i, model in enumerate(models):
                try:
                    response = await self._execute_generate_content(
                        model=model,
                        contents=prompt,
                        config=config
                    )
                    break
                except Exception as e:
                    last_error = e
                    if not is_overload_or_spike(e):
                        logger.error(f"Erro irrecuperável em generate_json com {model}: {e}")
                        raise e

                    next_model = models[i + 1] if i + 1 < len(models) else models[0]
                    logger.warning(
                        f"⚠️ [LLM JSON Fallback R{attempt_round + 1}] Modelo {model} indisponível ({getattr(e, 'code', '503/spikes')}). "
                        f"Tentando {next_model}..."
                    )
            if response is not None:
                break

        if response is None:
            if last_error:
                raise last_error
            raise RuntimeError("Nenhum modelo respondeu ao generate_json após rodadas de fallback.")

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
