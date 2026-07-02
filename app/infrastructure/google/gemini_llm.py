from typing import Any, Type
from google import genai
from google.genai import types
from google.genai.errors import APIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from app.application.interfaces.llm_gateway import LLMGateway
from app.core.config import settings

def is_retryable_error(exception: Exception) -> bool:
    if isinstance(exception, APIError):
        # Retentar para erros de servidor 5xx e rate limit 429
        return exception.code in [429, 500, 503, 504]
    return False

class GeminiLLM(LLMGateway):
    """Implementação concreta do LLMGateway usando o SDK google-genai do Google."""

    def __init__(self) -> None:
        self.client = genai.Client(api_key=settings.google_api_key)
        self.lite_model = "gemini-2.5-flash"
        self.premium_model = "gemini-2.5-pro"  # Premium model para tarefas que exigem raciocínio complexo e síntese de fontes

    @retry(
        retry=retry_if_exception(is_retryable_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True
    )
    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        use_premium_model: bool = False
    ) -> str:
        model = self.premium_model if use_premium_model else self.lite_model
        
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction
        )
        
        response = await self.client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=config
        )
        return response.text or ""

    @retry(
        retry=retry_if_exception(is_retryable_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True
    )
    async def generate_json(
        self,
        prompt: str,
        response_schema: Type[Any],
        system_instruction: str | None = None,
        temperature: float = 0.1,
        use_premium_model: bool = False
    ) -> Any:
        model = self.premium_model if use_premium_model else self.lite_model
        
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=response_schema
        )
        
        response = await self.client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=config
        )
        
        # O SDK preenche e retorna o objeto diretamente no formato do schema se especificado
        # mas como retornamos Any, convertemos de volta de JSON ou instanciamos se Pydantic
        import json
        text_data = response.text or "{}"
        
        # Se for um modelo Pydantic, instanciar a partir do dicionário JSON
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
        
        # Extrair valores dos embeddings
        if response.embeddings:
            return response.embeddings[0].values
        return []
