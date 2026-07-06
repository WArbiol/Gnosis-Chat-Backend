import asyncio
from datetime import datetime, timedelta
from supabase import Client
from app.application.interfaces.database_gateway import DatabaseGateway
from app.schemas.user import UserProfile, PlanEnum
from app.schemas.chat import CitationDraft

class SupabaseDatabase(DatabaseGateway):
    """Implementação do DatabaseGateway utilizando a API / SDK do Supabase com Service Role."""

    def __init__(self, client: Client) -> None:
        self.client = client

    async def get_user_profile(self, user_id: str) -> UserProfile:
        from app.core.config import settings
        # Bypass imediato para tokens de teste
        if settings.app_env == "development" and (user_id.startswith("test-") or "user-token" in user_id or "test" in user_id):
            return UserProfile(
                id=user_id,
                email=f"{user_id}@gnosis.chat",
                plan=PlanEnum.BASIC,
                chamber_level=1,
                question_count=0
            )

        try:
            loop = asyncio.get_running_loop()
            
            # Chamada síncrona envelopada em executor
            response = await loop.run_in_executor(
                None,
                lambda: self.client.table("users")
                .select("id, email, avatar_url, plan, chamber_level, question_count")
                .eq("id", user_id)
                .execute()
            )
            
            if not response.data:
                raise ValueError(f"Usuário com ID {user_id} não encontrado no banco.")
                
            data = response.data[0]
            return UserProfile(
                id=str(data["id"]),
                email=data["email"],
                avatar_url=data.get("avatar_url"),
                plan=PlanEnum(data["plan"]),
                chamber_level=int(data["chamber_level"]),
                question_count=int(data["question_count"])
            )
        except Exception as e:
            if settings.app_env == "development":
                print(f"DEBUG DB: Supabase get_user_profile falhou ({e}). Usando perfil mockado.")
                return UserProfile(
                    id=user_id,
                    email=f"{user_id}@gnosis.chat",
                    plan=PlanEnum.BASIC,
                    chamber_level=1,
                    question_count=0
                )
            raise e

    async def increment_user_question_count(self, user_id: str) -> None:
        from app.core.config import settings
        if settings.app_env == "development" and (user_id.startswith("test-") or "user-token" in user_id or "test" in user_id):
            return

        try:
            loop = asyncio.get_running_loop()
            
            # Recupera valor atual
            profile = await self.get_user_profile(user_id)
            new_count = profile.question_count + 1
            
            await loop.run_in_executor(
                None,
                lambda: self.client.table("users")
                .update({"question_count": new_count})
                .eq("id", user_id)
                .execute()
            )
        except Exception as e:
            if settings.app_env == "development":
                print(f"DEBUG DB: Supabase increment_user_question_count falhou ({e}). Ignorando em dev.")
                return
            raise e

    async def count_user_messages_in_last_7_days(self, user_id: str) -> int:
        from app.core.config import settings
        if settings.app_env == "development" and (user_id.startswith("test-") or "user-token" in user_id or "test" in user_id):
            return 0

        try:
            loop = asyncio.get_running_loop()
            
            # ISO format do timestamp de 7 dias atrás
            seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
            
            # Query: Conta mensagens do usuário feitas nas conversas dele
            response = await loop.run_in_executor(
                None,
                lambda: self.client.table("messages")
                .select("id, created_at, role, conversations!inner(user_id)")
                .eq("role", "user")
                .eq("conversations.user_id", user_id)
                .gte("created_at", seven_days_ago)
                .execute()
            )
            
            return len(response.data)
        except Exception as e:
            if settings.app_env == "development":
                print(f"DEBUG DB: Supabase count_user_messages_in_last_7_days falhou ({e}). Retornando 0 em dev.")
                return 0
            raise e

    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        route: str | None = None,
        token_count: int | None = None
    ) -> str:
        loop = asyncio.get_running_loop()
        
        payload = {
            "conversation_id": conversation_id,
            "role": role,
            "content": content
        }
        if route is not None:
            payload["route"] = route
        if token_count is not None:
            payload["token_count"] = token_count
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self.client.table("messages")
                .insert(payload)
                .execute()
            )
            
            if not response.data:
                raise RuntimeError("Falha ao salvar mensagem no Supabase.")
                
            return str(response.data[0]["id"])
        except Exception as e:
            from app.core.config import settings
            if settings.app_env == "development":
                print(f"DEBUG DB: Supabase messages table not reachable ({e}). Mocking message ID.")
                return "msg-mock-123"
            raise

    async def get_recent_messages(
        self,
        conversation_id: str,
        limit: int = 10
    ) -> list[dict[str, str]]:
        from app.core.config import settings

        try:
            loop = asyncio.get_running_loop()

            response = await loop.run_in_executor(
                None,
                lambda: self.client.table("messages")
                .select("role, content")
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )

            if not response.data:
                return []

            # Inverte para ordem cronológica (mais antiga → mais recente)
            messages = [
                {"role": row["role"], "content": row["content"]}
                for row in reversed(response.data)
            ]
            return messages

        except Exception as e:
            if settings.app_env == "development":
                print(f"DEBUG DB: get_recent_messages falhou ({e}). Retornando lista vazia.")
                return []
            raise

    async def save_citations(
        self,
        message_id: str,
        citations: list[CitationDraft]
    ) -> None:
        if not citations:
            return
            
        loop = asyncio.get_running_loop()
        
        # Formata o payload de inserção em lote
        payload = []
        for idx, cit in enumerate(citations):
            # No Supabase o campo é pdf_name. Salvamos o nome do livro
            payload.append({
                "message_id": message_id,
                "pdf_name": cit.book_name,
                "page": cit.page,
                "snippet": cit.snippet,
                "sort_order": idx
            })
        try:
            await loop.run_in_executor(
                None,
                lambda: self.client.table("citations")
                .insert(payload)
                .execute()
            )
        except Exception as e:
            from app.core.config import settings
            if settings.app_env == "development":
                print(f"DEBUG DB: Supabase citations table not reachable ({e}). Mocking citation save.")
                return
            raise
