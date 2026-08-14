import asyncio
from datetime import datetime, timezone, timedelta

import stripe

from app.core.config import settings
from app.core.dependencies import get_supabase_client

stripe.api_key = settings.stripe_secret_key

def get_price_to_plan() -> dict[str, str]:
    """Dynamic mapping of Stripe Price ID -> internal plan name."""
    mapping = {
        # Live Production Price IDs
        "price_1U4MJPPe2nJIREqqHWwJNL4A": "basic",
        "price_1U4MJOPe2nJIREqq7ZIhgxlC": "premium",
        # Test Price IDs
        "price_1T5XKvB1ESQiEiyTMhGeLFCt": "basic",
        "price_1T5XM3B1ESQiEiyTKJOXdvmq": "premium",
    }
    if settings.stripe_price_basic:
        mapping[settings.stripe_price_basic] = "basic"
    if settings.stripe_price_premium:
        mapping[settings.stripe_price_premium] = "premium"
    return mapping


class PriceToPlanDict(dict):
    def __getitem__(self, key):
        return get_price_to_plan()[key]

    def get(self, key, default=None):
        return get_price_to_plan().get(key, default)

    def __contains__(self, key):
        return key in get_price_to_plan()

    def values(self):
        return get_price_to_plan().values()



PRICE_TO_PLAN = PriceToPlanDict()



async def get_or_create_stripe_customer(user_id: str, email: str) -> str:
    """Return existing stripe_customer_id or create a new Stripe Customer."""
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    response = await loop.run_in_executor(
        None,
        lambda: client.table("users")
        .select("stripe_customer_id")
        .eq("id", user_id)
        .single()
        .execute(),
    )

    existing_id = response.data.get("stripe_customer_id") if response.data else None
    if existing_id:
        return existing_id

    # Create customer in Stripe
    customer = await loop.run_in_executor(
        None,
        lambda: stripe.Customer.create(
            email=email,
            metadata={"supabase_user_id": user_id},
        ),
    )

    # Persist stripe_customer_id
    await loop.run_in_executor(
        None,
        lambda: client.table("users")
        .update({"stripe_customer_id": customer.id})
        .eq("id", user_id)
        .execute(),
    )

    return customer.id


async def create_checkout_session(user_id: str, email: str, price_id: str) -> str:
    """Create a Stripe Checkout Session and return the hosted URL, or modify an existing subscription."""
    if price_id not in PRICE_TO_PLAN:
        raise ValueError(f"Invalid price_id: {price_id}")

    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Check if user already has an active subscription
    user_data = await loop.run_in_executor(
        None,
        lambda: client.table("users")
        .select("stripe_subscription_id, subscription_status")
        .eq("id", user_id)
        .single()
        .execute(),
    )
    user_record = user_data.data if user_data.data else {}
    subscription_id = user_record.get("stripe_subscription_id")
    sub_status = user_record.get("subscription_status")

    if subscription_id and sub_status == "active":
        # Modify the subscription directly on Stripe
        sub = await loop.run_in_executor(
            None,
            lambda: stripe.Subscription.retrieve(subscription_id),
        )
        if getattr(sub, "status", None) in ("active", "trialing"):
            items = getattr(sub, "items", None)
            items_data = getattr(items, "data", []) if items else []
            if items_data:
                sub_item_id = items_data[0].id
                await loop.run_in_executor(
                    None,
                    lambda: stripe.Subscription.modify(
                        subscription_id,
                        items=[{
                            "id": sub_item_id,
                            "price": price_id,
                        }],
                        proration_behavior="always_invoice",
                    ),
                )
                plan = PRICE_TO_PLAN.get(price_id, "free")
                await loop.run_in_executor(
                    None,
                    lambda: get_supabase_client().table("users")
                    .update({
                        "plan": plan,
                        "subscription_status": "active",
                        "subscription_provider": "stripe",
                    })
                    .eq("id", user_id)
                    .execute(),
                )
                return "updated"

    # Otherwise, create a new Stripe checkout session
    customer_id = await get_or_create_stripe_customer(user_id, email)

    base_url = "https://gnosischat.com"
    if not settings.is_production and settings.cors_origins:
        base_url = settings.cors_origins[0].rstrip("/")

    plan = PRICE_TO_PLAN.get(price_id, "free")
    session = await loop.run_in_executor(
        None,
        lambda: stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{base_url}/#/subscription?success=true&plan={plan}",
            cancel_url=f"{base_url}/#/subscription",
            metadata={"supabase_user_id": user_id},
        ),
    )

    return session.url


async def create_customer_portal_session(user_id: str) -> str:
    """Create a Stripe Billing Portal session so the user can manage their subscription."""
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    response = await loop.run_in_executor(
        None,
        lambda: client.table("users")
        .select("stripe_customer_id")
        .eq("id", user_id)
        .single()
        .execute(),
    )

    customer_id = response.data.get("stripe_customer_id") if response.data else None
    if not customer_id:
        raise ValueError("User has no Stripe customer record. Subscribe first.")

    base_url = "https://gnosischat.com"
    if not settings.is_production and settings.cors_origins:
        base_url = settings.cors_origins[0].rstrip("/")

    portal_session = await loop.run_in_executor(
        None,
        lambda: stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{base_url}/",
        ),
    )

    return portal_session.url


async def handle_webhook(payload: bytes, signature: str) -> None:
    """Verify Stripe webhook signature and process subscription events."""
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, settings.stripe_webhook_secret
        )
    except stripe.SignatureVerificationError as e:
        raise ValueError(f"Invalid webhook signature: {e}") from e

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data)
    elif event_type == "invoice.payment_succeeded":
        await _handle_invoice_paid(data)
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data)
    else:
        print(f"STRIPE WEBHOOK: Unhandled event type: {event_type}")


async def _handle_checkout_completed(session) -> None:
    """First-time checkout completed — activate the subscription."""
    customer_id = getattr(session, "customer", None)
    subscription_id = getattr(session, "subscription", None)
    if not customer_id or not subscription_id:
        return

    loop = asyncio.get_running_loop()

    # Fetch subscription details to get the price and period end
    sub = await loop.run_in_executor(
        None,
        lambda: stripe.Subscription.retrieve(subscription_id),
    )

    items = getattr(sub, "items", None)
    items_data = getattr(items, "data", []) if items else []
    price_id = None
    period_end_timestamp = None

    if items_data:
        first_item = items_data[0]
        price = getattr(first_item, "price", None)
        price_id = getattr(price, "id", None) if price else None
        period_end_timestamp = getattr(first_item, "current_period_end", None)

    # Fallback to subscription root just in case
    if not period_end_timestamp:
        period_end_timestamp = getattr(sub, "current_period_end", None)

    plan = PRICE_TO_PLAN.get(price_id, "free") if price_id else "free"
    
    if period_end_timestamp:
        period_end = datetime.fromtimestamp(period_end_timestamp, tz=timezone.utc).isoformat()
    else:
        period_end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    client = get_supabase_client()
    await loop.run_in_executor(
        None,
        lambda: client.table("users")
        .update({
            "plan": plan,
            "stripe_subscription_id": subscription_id,
            "subscription_status": "active",
            "subscription_provider": "stripe",
            "current_period_end": period_end,
        })
        .eq("stripe_customer_id", customer_id)
        .execute(),
    )
    print(f"STRIPE WEBHOOK: checkout.session.completed → plan={plan}, customer={customer_id}")


async def _handle_invoice_paid(invoice) -> None:
    """Recurring payment succeeded — extend the period."""
    customer_id = getattr(invoice, "customer", None)
    subscription_id = getattr(invoice, "subscription", None)
    if not customer_id or not subscription_id:
        return

    loop = asyncio.get_running_loop()

    sub = await loop.run_in_executor(
        None,
        lambda: stripe.Subscription.retrieve(subscription_id),
    )

    items = getattr(sub, "items", None)
    items_data = getattr(items, "data", []) if items else []
    period_end_timestamp = None

    if items_data:
        period_end_timestamp = getattr(items_data[0], "current_period_end", None)

    if not period_end_timestamp:
        period_end_timestamp = getattr(sub, "current_period_end", None)

    if period_end_timestamp:
        period_end = datetime.fromtimestamp(period_end_timestamp, tz=timezone.utc).isoformat()
    else:
        period_end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    client = get_supabase_client()
    await loop.run_in_executor(
        None,
        lambda: client.table("users")
        .update({
            "subscription_status": "active",
            "subscription_provider": "stripe",
            "current_period_end": period_end,
        })
        .eq("stripe_customer_id", customer_id)
        .execute(),
    )
    print(f"STRIPE WEBHOOK: invoice.payment_succeeded → renewed, customer={customer_id}")


async def _handle_subscription_updated(subscription) -> None:
    """Subscription status or plan changed."""
    customer_id = getattr(subscription, "customer", None)
    status = getattr(subscription, "status", None)
    subscription_id = getattr(subscription, "id", None)
    if not customer_id or not status:
        return

    loop = asyncio.get_running_loop()

    items = getattr(subscription, "items", None)
    items_data = getattr(items, "data", []) if items else []
    price_id = None
    period_end_timestamp = None

    if items_data:
        first_item = items_data[0]
        price = getattr(first_item, "price", None)
        price_id = getattr(price, "id", None) if price else None
        period_end_timestamp = getattr(first_item, "current_period_end", None)

    if not period_end_timestamp:
        period_end_timestamp = getattr(subscription, "current_period_end", None)

    plan = PRICE_TO_PLAN.get(price_id, "free") if price_id else "free"
    
    # If the subscription is canceled or status is incomplete_expired, revert to free
    if status in ("canceled", "incomplete_expired"):
        plan = "free"

    cancel_at_period_end = getattr(subscription, "cancel_at_period_end", False)
    if cancel_at_period_end and status == "active":
        status = "canceled"

    update_data = {
        "subscription_status": status,
        "plan": plan,
        "subscription_provider": "stripe",
    }
    if period_end_timestamp:
        update_data["current_period_end"] = datetime.fromtimestamp(period_end_timestamp, tz=timezone.utc).isoformat()
    if subscription_id:
        update_data["stripe_subscription_id"] = subscription_id

    client = get_supabase_client()
    await loop.run_in_executor(
        None,
        lambda: client.table("users")
        .update(update_data)
        .eq("stripe_customer_id", customer_id)
        .execute(),
    )
    print(f"STRIPE WEBHOOK: customer.subscription.updated → plan={plan}, status={status}, customer={customer_id}")


async def cancel_subscription(user_id: str) -> None:
    """Cancel the active Stripe subscription at period end so user keeps paid access until current_period_end."""
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    user_data = await loop.run_in_executor(
        None,
        lambda: client.table("users")
        .select("stripe_subscription_id, subscription_status")
        .eq("id", user_id)
        .single()
        .execute(),
    )
    user_record = user_data.data if user_data.data else {}
    subscription_id = user_record.get("stripe_subscription_id")
    sub_status = user_record.get("subscription_status")

    if not subscription_id or sub_status == "free":
        raise ValueError("Nenhuma assinatura ativa encontrada para cancelamento.")

    await loop.run_in_executor(
        None,
        lambda: stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True,
        ),
    )

    await loop.run_in_executor(
        None,
        lambda: get_supabase_client().table("users")
        .update({
            "subscription_status": "canceled",
        })
        .eq("id", user_id)
        .execute(),
    )




async def _handle_subscription_deleted(subscription) -> None:
    """Subscription fully canceled and expired — revert to free."""
    customer_id = getattr(subscription, "customer", None)
    if not customer_id:
        return

    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    await loop.run_in_executor(
        None,
        lambda: client.table("users")
        .update({
            "plan": "free",
            "subscription_status": "canceled",
            "stripe_subscription_id": None,
            "current_period_end": None,
        })
        .eq("stripe_customer_id", customer_id)
        .execute(),
    )
    print(f"STRIPE WEBHOOK: customer.subscription.deleted → reverted to free, customer={customer_id}")
