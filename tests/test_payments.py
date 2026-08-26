import json
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.core.security import get_current_user
from app.schemas.user import UserProfile, PlanEnum


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def paid_user():
    return UserProfile(
        id="user-paid-456",
        email="paid@gnosis.chat",
        plan=PlanEnum.BASIC,
        stripe_customer_id="cus_test123",
        subscription_status="active",
    )


@pytest.fixture
def free_user():
    return UserProfile(
        id="user-free-789",
        email="free@gnosis.chat",
        plan=PlanEnum.FREE,
    )


# ---------------------------------------------------------------------------
# POST /payments/checkout
# ---------------------------------------------------------------------------

class TestCheckout:
    @pytest.mark.asyncio
    async def test_checkout_unauthenticated(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/payments/checkout",
            json={"price_id": "price_test"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_checkout_invalid_price_id(self, client: AsyncClient, free_user):
        app.dependency_overrides[get_current_user] = lambda: free_user

        with patch(
            "app.services.payment_service.create_checkout_session",
            side_effect=ValueError("Invalid price_id: price_fake"),
        ):
            response = await client.post(
                "/api/v1/payments/checkout",
                json={"price_id": "price_fake"},
            )

        assert response.status_code == 400
        assert "Invalid price_id" in response.json()["message"]
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_checkout_success(self, client: AsyncClient, free_user):
        app.dependency_overrides[get_current_user] = lambda: free_user

        with patch(
            "app.services.payment_service.create_checkout_session",
            return_value="https://checkout.stripe.com/test-session",
        ):
            response = await client.post(
                "/api/v1/payments/checkout",
                json={"price_id": "price_test_basic"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["checkout_url"] == "https://checkout.stripe.com/test-session"
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_checkout_missing_price_id(self, client: AsyncClient, free_user):
        app.dependency_overrides[get_current_user] = lambda: free_user

        response = await client.post(
            "/api/v1/payments/checkout",
            json={},
        )

        assert response.status_code == 422  # Validation error
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /payments/customer-portal
# ---------------------------------------------------------------------------

class TestCustomerPortal:
    @pytest.mark.asyncio
    async def test_portal_unauthenticated(self, client: AsyncClient):
        response = await client.post("/api/v1/payments/customer-portal")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_portal_free_user_no_stripe_id(self, client: AsyncClient, free_user):
        app.dependency_overrides[get_current_user] = lambda: free_user

        with patch(
            "app.services.payment_service.create_customer_portal_session",
            side_effect=ValueError("User has no Stripe customer record. Subscribe first."),
        ):
            response = await client.post("/api/v1/payments/customer-portal")

        assert response.status_code == 400
        assert "Subscribe first" in response.json()["message"]
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_portal_success(self, client: AsyncClient, paid_user):
        app.dependency_overrides[get_current_user] = lambda: paid_user

        with patch(
            "app.services.payment_service.create_customer_portal_session",
            return_value="https://billing.stripe.com/portal-session",
        ):
            response = await client.post("/api/v1/payments/customer-portal")

        assert response.status_code == 200
        data = response.json()
        assert data["portal_url"] == "https://billing.stripe.com/portal-session"
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /payments/webhook
# ---------------------------------------------------------------------------

class TestWebhook:
    @pytest.mark.asyncio
    async def test_webhook_invalid_signature(self, client: AsyncClient):
        with patch(
            "app.services.payment_service.handle_webhook",
            side_effect=ValueError("Invalid webhook signature"),
        ):
            response = await client.post(
                "/api/v1/payments/webhook",
                content=b'{"type": "test"}',
                headers={"stripe-signature": "bad_sig"},
            )

        assert response.status_code == 400
        assert "Invalid webhook signature" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_webhook_success(self, client: AsyncClient):
        with patch(
            "app.services.payment_service.handle_webhook",
            return_value=None,
        ):
            response = await client.post(
                "/api/v1/payments/webhook",
                content=b'{"type": "checkout.session.completed"}',
                headers={"stripe-signature": "test_sig_valid"},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestRevenueCatWebhook:
    @pytest.mark.asyncio
    async def test_revenuecat_webhook_invalid_auth(self, client: AsyncClient):
        with patch(
            "app.services.payment_service.handle_revenuecat_webhook",
            side_effect=ValueError("Invalid RevenueCat authorization header"),
        ):
            response = await client.post(
                "/api/v1/payments/revenuecat-webhook",
                json={"event": {"type": "INITIAL_PURCHASE"}},
                headers={"authorization": "Bearer bad_token"},
            )

        assert response.status_code == 401
        assert "Invalid RevenueCat authorization header" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_revenuecat_webhook_success(self, client: AsyncClient):
        with patch(
            "app.services.payment_service.handle_revenuecat_webhook",
            return_value=None,
        ):
            response = await client.post(
                "/api/v1/payments/revenuecat-webhook",
                json={"event": {"type": "INITIAL_PURCHASE", "app_user_id": "u123", "entitlement_ids": ["premium"]}},
                headers={"authorization": "Bearer rc_whsec_gnosis_2026_secure"},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Service layer: PRICE_TO_PLAN mapping
# ---------------------------------------------------------------------------

class TestPriceMapping:
    def test_price_to_plan_has_basic_and_premium(self):
        from app.services.payment_service import PRICE_TO_PLAN
        values = set(PRICE_TO_PLAN.values())
        assert "basic" in values
        assert "premium" in values

    def test_price_to_plan_does_not_include_free(self):
        from app.services.payment_service import PRICE_TO_PLAN
        assert "free" not in PRICE_TO_PLAN.values()


# ---------------------------------------------------------------------------
# Schema: UserProfile with Stripe fields
# ---------------------------------------------------------------------------

class TestUserProfileSchema:
    def test_default_stripe_fields(self):
        profile = UserProfile(id="u1", email="a@b.com")
        assert profile.stripe_customer_id is None
        assert profile.subscription_status == "free"
        assert profile.current_period_end is None

    def test_stripe_fields_populated(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        profile = UserProfile(
            id="u2",
            email="b@b.com",
            stripe_customer_id="cus_123",
            subscription_status="active",
            current_period_end=now,
        )
        assert profile.stripe_customer_id == "cus_123"
        assert profile.subscription_status == "active"
        assert profile.current_period_end == now

    def test_plan_enum_serialization(self):
        profile = UserProfile(id="u3", email="c@b.com", plan=PlanEnum.PREMIUM)
        data = profile.model_dump()
        assert data["plan"] == "premium"
        assert data["subscription_status"] == "free"


# ---------------------------------------------------------------------------
# PlanLimits: INTERESTS removed
# ---------------------------------------------------------------------------

class TestPlanLimits:
    def test_question_limits_exist(self):
        from app.schemas.user import PlanLimits
        assert PlanLimits.get_question_limit(PlanEnum.FREE) == 3
        assert PlanLimits.get_question_limit(PlanEnum.BASIC) == 100
        assert PlanLimits.get_question_limit(PlanEnum.PREMIUM) == 1000

    def test_interests_removed(self):
        from app.schemas.user import PlanLimits
        assert not hasattr(PlanLimits, "INTERESTS")
        assert not hasattr(PlanLimits, "get_interest_limit")


# ---------------------------------------------------------------------------
# Service: handle_revenuecat_webhook
# ---------------------------------------------------------------------------

class TestRevenueCatService:
    @pytest.mark.asyncio
    async def test_handle_initial_purchase(self):
        from app.services.payment_service import handle_revenuecat_webhook

        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()
        mock_execute = MagicMock()

        mock_supabase.table.return_value = mock_table
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_eq
        mock_eq.execute.return_value = mock_execute

        payload = {
            "event": {
                "type": "INITIAL_PURCHASE",
                "app_user_id": "user-uuid-123",
                "product_id": "gnosis_premium_monthly",
                "entitlement_ids": ["premium"],
                "expiration_at_ms": 1727275000000,
            }
        }

        with patch("app.services.payment_service.get_supabase_client", return_value=mock_supabase):
            await handle_revenuecat_webhook(payload, "Bearer rc_whsec_gnosis_2026_secure")

        mock_table.update.assert_called_once()
        update_arg = mock_table.update.call_args[0][0]
        assert update_arg["plan"] == "premium"
        assert update_arg["subscription_provider"] == "revenuecat"
        assert update_arg["subscription_status"] == "active"
        assert update_arg["question_count"] == 0
        assert "current_period_end" in update_arg
        mock_update.eq.assert_called_once_with("id", "user-uuid-123")

    @pytest.mark.asyncio
    async def test_handle_cancellation(self):
        from app.services.payment_service import handle_revenuecat_webhook

        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()

        mock_supabase.table.return_value = mock_table
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_eq

        payload = {
            "event": {
                "type": "CANCELLATION",
                "app_user_id": "user-uuid-123",
                "expiration_at_ms": 1727275000000,
            }
        }

        with patch("app.services.payment_service.get_supabase_client", return_value=mock_supabase):
            await handle_revenuecat_webhook(payload, "Bearer rc_whsec_gnosis_2026_secure")

        update_arg = mock_table.update.call_args[0][0]
        assert update_arg["subscription_status"] == "canceled"
        assert "plan" not in update_arg  # keeps current plan until expiration

    @pytest.mark.asyncio
    async def test_handle_expiration(self):
        from app.services.payment_service import handle_revenuecat_webhook

        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()

        mock_supabase.table.return_value = mock_table
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_eq

        payload = {
            "event": {
                "type": "EXPIRATION",
                "app_user_id": "user-uuid-123",
            }
        }

        with patch("app.services.payment_service.get_supabase_client", return_value=mock_supabase):
            await handle_revenuecat_webhook(payload, "Bearer rc_whsec_gnosis_2026_secure")

        update_arg = mock_table.update.call_args[0][0]
        assert update_arg["plan"] == "free"
        assert update_arg["subscription_status"] == "canceled"
        assert update_arg["current_period_end"] is None
