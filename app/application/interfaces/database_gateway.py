from abc import ABC, abstractmethod
from app.schemas.user import UserProfile
from app.schemas.chat import CitationDraft

class DatabaseGateway(ABC):
    """Interface abstrata para persistência de dados relacionais (Supabase / PostgreSQL)."""

    @abstractmethod
    async def get_user_profile(self, user_id: str) -> UserProfile:
        """Recupera o perfil atualizado do usuário, incluindo plano e câmara."""
        pass

    @abstractmethod
    async def increment_user_question_count(self, user_id: str) -> None:
        """Incrementa a cota de perguntas realizadas do usuário em 1."""
        pass

    @abstractmethod
    async def count_user_messages_in_last_7_days(self, user_id: str) -> int:
        """Retorna o número de mensagens enviadas pelo usuário nos últimos 7 dias."""
        pass

    @abstractmethod
    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        route: str | None = None,
        token_count: int | None = None
    ) -> str:
        """Salva uma mensagem da conversa e retorna o ID gerado (message_id)."""
        pass

    @abstractmethod
    async def get_recent_messages(
        self,
        conversation_id: str,
        limit: int = 10
    ) -> list[dict[str, str]]:
        """Recupera as últimas `limit` mensagens da conversa, ordenadas cronologicamente.
        
        Retorna uma lista de dicts no formato [{"role": "user", "content": "..."}, ...].
        """
        pass

    @abstractmethod
    async def save_citations(
        self,
        message_id: str,
        citations: list[CitationDraft]
    ) -> None:
        """Salva as citações vinculadas a uma mensagem no banco de dados."""
        pass

    @abstractmethod
    async def get_second_chamber_catalog(self) -> list[dict]:
        """Retorna todos os livros e autores cadastrados na Segunda Câmara."""
        pass
