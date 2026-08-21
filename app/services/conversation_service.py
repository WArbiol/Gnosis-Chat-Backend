import asyncio
from datetime import datetime
from uuid import UUID

from supabase import Client

from app.schemas.conversation import (
    ConversationDetail,
    ConversationResponse,
    MessageResponse,
    PaginatedResponse,
    Pagination,
)


class ConversationService:
    def __init__(self, client: Client):
        self.client = client

    def _execute(self, query_builder_fn, max_retries: int = 3):
        from app.core.dependencies import get_supabase_client
        for attempt in range(max_retries):
            try:
                return query_builder_fn(self.client).execute()
            except Exception as e:
                err_str = f"{type(e).__name__}: {str(e)}"
                if ("RemoteProtocolError" in err_str or "ConnectionTerminated" in err_str or "httpcore" in err_str or "httpx" in err_str) and attempt < max_retries - 1:
                    print(f"DEBUG DB: Connection dropped ({err_str}), re-instantiating Supabase client (attempt {attempt + 1}/{max_retries})...")
                    self.client = get_supabase_client()
                    continue
                raise

    def list_conversations(self, limit: int = 20, cursor: str | None = None) -> PaginatedResponse[ConversationResponse]:
        def _build(client: Client):
            q = client.table("conversations").select("*").order("is_pinned", desc=True).order("updated_at", desc=True).limit(limit + 1)
            if cursor:
                q = q.lt("updated_at", cursor)
            return q

        result = self._execute(_build).data
        
        has_more = len(result) > limit
        if has_more:
            result.pop()
            
        next_cursor = result[-1]["updated_at"] if has_more and result else None
        
        conversations = [
            ConversationResponse(
                id=r["id"],
                user_id=r["user_id"],
                title=r["title"],
                is_pinned=r.get("is_pinned", False),
                created_at=datetime.fromisoformat(r["created_at"]),
                updated_at=datetime.fromisoformat(r["updated_at"]),
            ) for r in result
        ]
        
        return PaginatedResponse(
            data=conversations,
            pagination=Pagination(has_more=has_more, next_cursor=next_cursor)
        )

    def create_conversation(self, title: str, user_id: str) -> ConversationResponse:
        result = self._execute(
            lambda c: c.table("conversations").insert({"title": title, "user_id": user_id})
        ).data[0]
        
        return ConversationResponse(
            id=result["id"],
            user_id=result["user_id"],
            title=result["title"],
            is_pinned=result.get("is_pinned", False),
            created_at=datetime.fromisoformat(result["created_at"]),
            updated_at=datetime.fromisoformat(result["updated_at"]),
        )

    def get_conversation(self, conversation_id: str) -> ConversationDetail | None:
        # Fetch conversation
        conv_query = self._execute(
            lambda c: c.table("conversations").select("*").eq("id", conversation_id)
        ).data
        if not conv_query:
            return None
        conv_result = conv_query[0]
        user_id = conv_result.get("user_id")
        
        # Fetch initial messages (first page)
        msgs_result = self._execute(
            lambda c: c.table("messages").select("*, citations(id, message_id, pdf_name, page, sort_order)").eq("conversation_id", conversation_id).order("created_at", desc=False).limit(50)
        ).data
        
        from app.core.crypto import decrypt_message, encrypt_message

        messages = []
        for m in msgs_result:
            m["content"] = decrypt_message(m.get("content", ""), user_id)
            m["citations"] = m.get("citations", [])
            m["suggested_followups"] = m.get("suggested_followups") or []
            messages.append(MessageResponse(**m))
            
        return ConversationDetail(
            id=conv_result["id"],
            user_id=conv_result["user_id"],
            title=conv_result["title"],
            is_pinned=conv_result.get("is_pinned", False),
            created_at=datetime.fromisoformat(conv_result["created_at"]),
            updated_at=datetime.fromisoformat(conv_result["updated_at"]),
            messages=messages
        )

    def get_citation_snippet(self, citation_id: str) -> str | None:
        result = self._execute(
            lambda c: c.table("citations").select("id, snippet").eq("id", citation_id)
        ).data
        if not result:
            return None
        return result[0].get("snippet", "")

    def delete_conversation(self, conversation_id: str) -> None:
        self._execute(lambda c: c.table("conversations").delete().eq("id", conversation_id))

    def update_conversation(
        self, conversation_id: str, title: str | None = None, is_pinned: bool | None = None
    ) -> ConversationResponse:
        update_data = {}
        if title is not None:
            update_data["title"] = title
        if is_pinned is not None:
            update_data["is_pinned"] = is_pinned

        if not update_data:
            conv = self.get_conversation(conversation_id)
            if not conv:
                raise ValueError(f"Conversation {conversation_id} not found")
            return ConversationResponse(
                id=conv.id,
                user_id=conv.user_id,
                title=conv.title,
                is_pinned=conv.is_pinned,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )

        result = self._execute(
            lambda c: c.table("conversations").update(update_data).eq("id", conversation_id)
        ).data[0]
        return ConversationResponse(
            id=result["id"],
            user_id=result["user_id"],
            title=result["title"],
            is_pinned=result.get("is_pinned", False),
            created_at=datetime.fromisoformat(result["created_at"]),
            updated_at=datetime.fromisoformat(result["updated_at"]),
        )

    def list_messages(self, conversation_id: str, limit: int = 50, cursor: str | None = None) -> PaginatedResponse[MessageResponse]:
        from app.core.crypto import decrypt_message

        conv_query = self._execute(
            lambda c: c.table("conversations").select("user_id").eq("id", conversation_id)
        ).data
        user_id = conv_query[0].get("user_id") if conv_query else None

        def _build(client: Client):
            q = client.table("messages").select("*, citations(id, message_id, pdf_name, page, sort_order)").eq("conversation_id", conversation_id).order("created_at", desc=False).limit(limit + 1)
            if cursor:
                q = q.gt("created_at", cursor)
            return q

        result = self._execute(_build).data
        
        has_more = len(result) > limit
        if has_more:
            result.pop()
            
        next_cursor = result[-1]["created_at"] if has_more and result else None
        
        for m in result:
            m["content"] = decrypt_message(m.get("content", ""), user_id)
            
        messages = [MessageResponse(**m) for m in result]
        
        return PaginatedResponse(
            data=messages,
            pagination=Pagination(has_more=has_more, next_cursor=next_cursor)
        )

    def create_message(self, conversation_id: str, role: str, content: str, route: str = "", token_count: int = 0) -> MessageResponse:
        from app.core.crypto import encrypt_message

        conv_query = self._execute(
            lambda c: c.table("conversations").select("user_id").eq("id", conversation_id)
        ).data
        user_id = conv_query[0].get("user_id") if conv_query else None

        encrypted_content = encrypt_message(content, user_id)

        payload = {
            "conversation_id": conversation_id,
            "role": role,
            "content": encrypted_content,
            "route": route,
            "token_count": token_count
        }
        print(f"DEBUG DB: Inserting message: {payload}")
        try:
            result = self._execute(lambda c: c.table("messages").insert(payload)).data[0]
            print(f"DEBUG DB: Message inserted successfully: {result.get('id')}")
            result["content"] = content
            result["citations"] = []
            return MessageResponse(**result)
        except Exception as e:
            print(f"DEBUG DB: FAILED to insert message: {e}")
            raise

    async def generate_title_async(self, conversation_id: str, initial_message: str):
        """Asynchronously updates the conversation title based on the first message."""
        from app.agents.nodes.utils import get_llm
        
        # Simple heuristic fallback (e.g., first N chars)
        short_title = (initial_message[:30] + "...") if len(initial_message) > 30 else initial_message
        loop = asyncio.get_running_loop()
        
        try:
            llm = get_llm()
            prompt = f"Gere um título super curto e objetivo (máximo 3 a 5 palavras) para a seguinte dúvida de um usuário: '{initial_message}'"
            system_instruction = "Você é um gerador de títulos. Retorne APENAS o título, sem aspas, sem ponto final. Capitalize a primeira letra de cada palavra principal."
            
            generated_title = await llm.generate_text(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=0.5,
                use_premium_model=False
            )
            
            final_title = generated_title.strip().strip('"').strip("'")
            if not final_title or len(final_title) > 50:
                final_title = short_title
                
            await loop.run_in_executor(
                None,
                lambda: self._execute(lambda c: c.table("conversations").update({"title": final_title}).eq("id", conversation_id))
            )
        except Exception as e:
            print(f"Error generating title for {conversation_id}: {e}")
            await loop.run_in_executor(
                None,
                lambda: self._execute(lambda c: c.table("conversations").update({"title": short_title}).eq("id", conversation_id))
            )

