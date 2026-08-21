from fastapi import APIRouter

from app.api.v1 import auth, chat, citations, conversations, payments, pdfs

api_v1_router = APIRouter()

api_v1_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_v1_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_v1_router.include_router(citations.router, prefix="/citations", tags=["citations"])
api_v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(payments.router, prefix="/payments", tags=["payments"])
api_v1_router.include_router(pdfs.router, prefix="/pdfs", tags=["pdfs"])

