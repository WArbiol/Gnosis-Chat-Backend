from fastapi import APIRouter

from app.api.v1 import auth, chat, conversations, payments

api_v1_router = APIRouter()

api_v1_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_v1_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(payments.router, prefix="/payments", tags=["payments"])
