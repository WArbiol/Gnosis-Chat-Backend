async def create_checkout_session(user_id: str, price_id: str) -> str:
    """Create a Stripe Checkout Session and return the URL.

    TODO: implement Stripe checkout session creation
    """
    raise NotImplementedError("Stripe checkout not yet implemented")


async def handle_webhook(payload: bytes, signature: str) -> None:
    """Process Stripe webhook event and update user plan in Supabase.

    TODO: verify signature, parse event, update users table
    """
    raise NotImplementedError("Stripe webhook not yet implemented")
