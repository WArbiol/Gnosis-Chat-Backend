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

    def list_conversations(self, limit: int = 20, cursor: str | None = None) -> PaginatedResponse[ConversationResponse]:
        query = self.client.table("conversations").select("*").order("updated_at", desc=True).limit(limit + 1)
        if cursor:
            query = query.lt("updated_at", cursor)
            
        result = query.execute().data
        
        has_more = len(result) > limit
        if has_more:
            result.pop()
            
        next_cursor = result[-1]["updated_at"] if has_more and result else None
        
        conversations = [
            ConversationResponse(
                id=r["id"],
                user_id=r["user_id"],
                title=r["title"],
                created_at=datetime.fromisoformat(r["created_at"]),
                updated_at=datetime.fromisoformat(r["updated_at"]),
            ) for r in result
        ]
        
        return PaginatedResponse(
            data=conversations,
            pagination=Pagination(has_more=has_more, next_cursor=next_cursor)
        )

    def create_conversation(self, title: str, user_id: str) -> ConversationResponse:
        result = self.client.table("conversations").insert({
            "title": title,
            "user_id": user_id
        }).execute().data[0]
        
        return ConversationResponse(
            id=result["id"],
            user_id=result["user_id"],
            title=result["title"],
            created_at=datetime.fromisoformat(result["created_at"]),
            updated_at=datetime.fromisoformat(result["updated_at"]),
        )

    def get_conversation(self, conversation_id: str) -> ConversationDetail | None:
        from app.core.dependencies import get_supabase_client
        for attempt in range(2):
            try:
                # Fetch conversation
                conv_query = self.client.table("conversations").select("*").eq("id", conversation_id).execute().data
                if not conv_query:
                    return None
                conv_result = conv_query[0]
                
                # Fetch initial messages (first page)
                msgs_result = self.client.table("messages").select(
                    "*, citations(*)"
                ).eq("conversation_id", conversation_id).order("created_at", desc=False).limit(50).execute().data
                
                messages = []
                for m in msgs_result:
                    m["citations"] = m.get("citations", [])
                    m["suggested_followups"] = m.get("suggested_followups") or []
                    messages.append(MessageResponse(**m))
                    
                return ConversationDetail(
                    id=conv_result["id"],
                    user_id=conv_result["user_id"],
                    title=conv_result["title"],
                    created_at=datetime.fromisoformat(conv_result["created_at"]),
                    updated_at=datetime.fromisoformat(conv_result["updated_at"]),
                    messages=messages
                )
            except Exception as e:
                err_str = str(e)
                if ("RemoteProtocolError" in err_str or "ConnectionTerminated" in err_str or "httpcore" in err_str) and attempt == 0:
                    # Re-instantiate client to get a fresh HTTP/2 connection pool
                    self.client = get_supabase_client()
                    continue
                raise

    def delete_conversation(self, conversation_id: str) -> None:
        self.client.table("conversations").delete().eq("id", conversation_id).execute()

    def update_conversation(self, conversation_id: str, title: str) -> ConversationResponse:
        result = self.client.table("conversations").update({"title": title}).eq("id", conversation_id).execute().data[0]
        return ConversationResponse(**result)

    def list_messages(self, conversation_id: str, limit: int = 50, cursor: str | None = None) -> PaginatedResponse[MessageResponse]:
        query = self.client.table("messages").select("*, citations(*)").eq("conversation_id", conversation_id).order("created_at", desc=False).limit(limit + 1)
        
        if cursor:
            query = query.gt("created_at", cursor)
            
        result = query.execute().data
        
        has_more = len(result) > limit
        if has_more:
            result.pop()
            
        next_cursor = result[-1]["created_at"] if has_more and result else None
        
        messages = [MessageResponse(**m) for m in result]
        
        return PaginatedResponse(
            data=messages,
            pagination=Pagination(has_more=has_more, next_cursor=next_cursor)
        )

    def create_message(self, conversation_id: str, role: str, content: str, route: str = "", token_count: int = 0) -> MessageResponse:
        payload = {
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "route": route,
            "token_count": token_count
        }
        print(f"DEBUG DB: Inserting message: {payload}")
        try:
            result = self.client.table("messages").insert(payload).execute().data[0]
            print(f"DEBUG DB: Message inserted successfully: {result.get('id')}")
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
                lambda: self.client.table("conversations").update({"title": final_title}).eq("id", conversation_id).execute()
            )
        except Exception as e:
            print(f"Error generating title for {conversation_id}: {e}")
            await loop.run_in_executor(
                None,
                lambda: self.client.table("conversations").update({"title": short_title}).eq("id", conversation_id).execute()
            )
