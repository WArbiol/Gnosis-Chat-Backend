from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from app.core.security import get_current_user
from app.schemas.user import UserProfile
from app.services import payment_service

router = APIRouter()


class CheckoutRequest(BaseModel):
    price_id: str


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    user: UserProfile = Depends(get_current_user),
) -> dict:
    """Create a Stripe Checkout Session and return the hosted URL, or modify an existing subscription."""
    try:
        result = await payment_service.create_checkout_session(
            user_id=user.id,
            email=user.email,
            price_id=body.price_id,
        )
        if result == "updated":
            return {"status": "updated"}
        return {"checkout_url": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cancel")
async def cancel_subscription(
    user: UserProfile = Depends(get_current_user),
) -> dict:
    """Cancel the user's active Stripe subscription."""
    try:
        await payment_service.cancel_subscription(user_id=user.id)
        return {"status": "canceled"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/customer-portal")
async def customer_portal(
    user: UserProfile = Depends(get_current_user),
) -> dict:
    """Create a Stripe Billing Portal session for subscription management."""
    try:
        url = await payment_service.create_customer_portal_session(user_id=user.id)
        return {"portal_url": url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="stripe-signature"),
) -> dict:
    """Receive and process Stripe webhook events. No auth — validated by signature."""
    payload = await request.body()
    try:
        await payment_service.handle_webhook(payload, stripe_signature)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}
