from abc import ABC, abstractmethod
from app.application.interfaces.vector_store_gateway import ChunkResult

class RerankerGateway(ABC):
    """Interface abstrata para o serviço de Re-ranking (Vertex AI Ranking API)."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: list[ChunkResult],
        top_n: int = 10
    ) -> list[ChunkResult]:
        """Reordena e filtra os documentos com base na relevância para a query."""
        pass
