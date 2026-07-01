from typing import Any, Type
from google import genai
from google.genai import types
from app.application.interfaces.llm_gateway import LLMGateway
from app.core.config import settings

class GeminiLLM(LLMGateway):
    """Implementação concreta do LLMGateway usando o SDK google-genai do Google."""

    def __init__(self) -> None:
        self.client = genai.Client(api_key=settings.google_api_key)
        # Modelos
        self.lite_model = "gemini-2.5-flash"
        self.premium_model = "gemini-2.5-flash" # Pode ser gemini-2.5-pro se desejado maior profundidade

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
        
        # O SDK realiza chamadas síncronas bloqueantes por padrão nas funções normais.
        # Para manter o async do FastAPI, executamos no thread pool usando o loop de eventos.
        import asyncio
        loop = asyncio.get_running_loop()
        
        response = await loop.run_in_executor(
            None,
            lambda: self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=config
            )
        )
        return response.text or ""

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
        
        import asyncio
        loop = asyncio.get_running_loop()
        
        response = await loop.run_in_executor(
            None,
            lambda: self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=config
            )
        )
        
        # O SDK preenche e retorna o objeto diretamente no formato do schema se especificado
        # mas como retornamos Any, convertemos de volta de JSON ou instanciamos se Pydantic
        import json
        text_data = response.text or "{}"
        
        # Se for um modelo Pydantic, instanciar a partir do dicionário JSON
        if hasattr(response_schema, "model_validate_json"):
            return response_schema.model_validate_json(text_data)
        
        return json.loads(text_data)

    async def generate_embeddings(self, text: str) -> list[float]:
        import asyncio
        loop = asyncio.get_running_loop()
        
        response = await loop.run_in_executor(
            None,
            lambda: self.client.models.embed_content(
                model="gemini-embedding-001",
                contents=text
            )
        )
        
        # Extrair valores dos embeddings
        if response.embeddings:
            return response.embeddings[0].values
        return []
