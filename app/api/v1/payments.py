from fastapi import APIRouter, Depends, Header, Request

from app.core.security import get_current_user
from app.schemas.user import UserProfile
from app.services import payment_service

router = APIRouter()


@router.post("/checkout")
async def create_checkout(
    price_id: str,
    user: UserProfile = Depends(get_current_user),
) -> dict:
    url = await payment_service.create_checkout_session(user.id, price_id)
    return {"checkout_url": url}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="stripe-signature"),
) -> dict:
    payload = await request.body()
    await payment_service.handle_webhook(payload, stripe_signature)
    return {"status": "ok"}
