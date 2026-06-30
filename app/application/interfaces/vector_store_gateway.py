from abc import ABC, abstractmethod
from typing import Any, TypedDict

class ChunkResult(TypedDict):
    """Estrutura padrão de retorno de um chunk do Vector Store."""
    text: str
    book_name: str
    author: str
    page: int
    chamber: int
    chapter: str | None
    score: float

class VectorStoreGateway(ABC):
    """Interface abstrata para operações no Vector Database (Qdrant)."""

    @abstractmethod
    async def search_books(
        self,
        query_vector: list[float],
        limit: int = 30,
        books: list[str] | None = None,
        authors: list[str] | None = None,
        chamber_levels: list[int] | None = None,
        chapters: list[str] | None = None
    ) -> list[ChunkResult]:
        """Realiza busca vetorial na coleção de livros (gnosis_books)."""
        pass

    @abstractmethod
    async def search_user_interests(
        self,
        user_id: str,
        query_vector: list[float],
        limit: int = 5
    ) -> list[ChunkResult]:
        """Busca interesses do usuário na coleção user_interests."""
        pass

    @abstractmethod
    async def upsert_user_interest(
        self,
        user_id: str,
        interest_text: str,
        vector: list[float]
    ) -> None:
        """Adiciona ou atualiza um vetor de interesse para o usuário."""
        pass
