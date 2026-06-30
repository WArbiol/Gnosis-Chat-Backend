from app.schemas.chat import ChatRequest
from app.schemas.conversation import MessageResponse, ConversationResponse
from app.schemas.user import UserProfile
from app.core.dependencies import get_supabase_client
from app.services.conversation_service import ConversationService


async def ask(request: ChatRequest, user: UserProfile) -> MessageResponse:
    """Orchestrate the RAG pipeline for a user query and persist messages.
    """
    client = get_supabase_client()
    conv_service = ConversationService(client)
    
    # 1. Resolve conversation_id
    conversation_id = str(request.conversation_id) if request.conversation_id else None
    
    if not conversation_id:
        new_conv = conv_service.create_conversation("Nova conversa", user.id)
        conversation_id = str(new_conv.id)
        
    # 2. Persist user message optimistically
    print(f"DEBUG CHAT: Persisting user message for conv {conversation_id}")
    try:
        conv_service.create_message(
            conversation_id=conversation_id,
            role="user",
            content=request.query
        )
    except Exception as e:
        print(f"DEBUG CHAT: ERROR persisting user message: {e}")
        raise
        
    # 3. TODO: invoke pipeline.compiled_graph.ainvoke(...)
    # For now, simulate the AI reply
    route = "DIRECT"
    answer = "TODO: RAG pipeline not yet wired. Mensagem persistida!"
    token_count = 50
    citations = []
    
    # 4. Persist AI Assistant message 
    print(f"DEBUG CHAT: Persisting assistant message for conv {conversation_id}")
    try:
        ai_msg = conv_service.create_message(
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            route=route,
            token_count=token_count
        )
    except Exception as e:
        print(f"DEBUG CHAT: ERROR persisting assistant message: {e}")
        raise
    
    # 5. TODO: Save citations to DB (if any)
    # The current stub returns an empty citation block
    
    # If this is the FIRST message in a new conversation, title it asynchronously
    # We check if request.conversation_id was None OR if the current title is still "Nova conversa"
    try:
        conv_data = conv_service.get_conversation(conversation_id)
        if request.conversation_id is None or conv_data.title == "Nova conversa":
            import asyncio
            asyncio.create_task(conv_service.generate_title_async(conversation_id, request.query))
    except Exception as e:
        print(f"DEBUG CHAT: Error during title generation check: {e}")

    return ai_msg
