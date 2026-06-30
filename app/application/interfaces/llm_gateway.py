from abc import ABC, abstractmethod
from typing import Any, Type

class LLMGateway(ABC):
    """Interface abstrata para chamadas de LLM (Inference e Synthesis)."""

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        use_premium_model: bool = False
    ) -> str:
        """Gera um texto simples a partir do prompt."""
        pass

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        response_schema: Type[Any],
        system_instruction: str | None = None,
        temperature: float = 0.1,
        use_premium_model: bool = False
    ) -> Any:
        """Gera uma resposta estruturada em JSON mapeada para um modelo Pydantic/TypedDict."""
        pass

    @abstractmethod
    async def generate_embeddings(self, text: str) -> list[float]:
        """Gera os embeddings vetoriais para um determinado texto."""
        pass

