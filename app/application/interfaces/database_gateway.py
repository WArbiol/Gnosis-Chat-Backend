from abc import ABC, abstractmethod
from app.schemas.user import UserProfile
from app.schemas.conversation import CitationResponse

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
    async def save_citations(
        self,
        message_id: str,
        citations: list[CitationResponse]
    ) -> None:
        """Salva as citações vinculadas a uma mensagem no banco de dados."""
        pass
