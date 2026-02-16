"""Billing middleware and endpoints for subscription management.

Web-only (REQUIRE_AUTH) — desktop mode skips billing entirely.
Uses asyncpg to call PostgreSQL RPC functions defined in the billing migration.
Uses Stripe Python SDK directly for checkout, portal, cancel, and webhooks.
"""

import logging
import os
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "").lower() == "true"
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Initialize Stripe
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# ---------------------------------------------------------------------------
# Price ID ↔ Tier mapping
# ---------------------------------------------------------------------------

_PRICE_TO_TIER: dict[str, str] = {
    "price_1T17lIHSjjrILQoYBzwcGV2C": "starter",       # monthly
    "price_1T17O6HSjjrILQoYNciwe0Iv": "starter",       # annual
    "price_1T17PKHSjjrILQoY3x9oAmKz": "professional",  # monthly
    "price_1T17joHSjjrILQoYNCLkkCMC": "professional",  # annual
    "price_1T17PlHSjjrILQoYUmFKq6a7": "unlimited",     # monthly
    "price_1T17bjHSjjrILQoYAMSSIPiK": "unlimited",     # annual
}

_TIER_TO_PRICES: dict[str, dict[str, str]] = {
    "starter": {
        "monthly": "price_1T17lIHSjjrILQoYBzwcGV2C",
        "annual": "price_1T17O6HSjjrILQoYNciwe0Iv",
    },
    "professional": {
        "monthly": "price_1T17PKHSjjrILQoY3x9oAmKz",
        "annual": "price_1T17joHSjjrILQoYNCLkkCMC",
    },
    "unlimited": {
        "monthly": "price_1T17PlHSjjrILQoYUmFKq6a7",
        "annual": "price_1T17bjHSjjrILQoYAMSSIPiK",
    },
}

# ---------------------------------------------------------------------------
# Feature → counter mapping
# ---------------------------------------------------------------------------

_FEATURE_MAP: dict[str, str] = {
    "/analyze/explain": "report_count",
    "/analyze/explain-stream": "report_count",
    "/analyze/compare": "comparison_count",
    "/analyze/synthesize": "deep_analysis_count",
    "/letters/generate": "letter_count",
}

_LIMIT_MAP: dict[str, str] = {
    "report_count": "monthly_reports",
    "deep_analysis_count": "monthly_deep_analysis",
    "letter_count": "monthly_letters",
    "comparison_count": "monthly_reports",  # comparisons count toward reports
}

_FEATURE_DISPLAY: dict[str, str] = {
    "report_count": "reports",
    "deep_analysis_count": "deep analyses",
    "letter_count": "letters",
    "comparison_count": "reports",
}

# Paths that are never metered
_SKIP_PREFIXES = (
    "/health",
    "/settings",
    "/history",
    "/templates",
    "/teaching-points",
    "/auth",
    "/consent",
    "/onboarding",
    "/billing",
    "/account",
    "/sync",
    "/extract",
    "/detect",
    "/export",
    "/glossary",
    "/test-types",
    "/analyze/detect-type",
    "/analyze/parse",
    "/analyze/classify-input",
    "/analyze/patient-fingerprints",
    "/analyze/interpret",
)

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _get_user_id(request: Request) -> str:
    """Extract user_id from request state. Raises 401 if missing."""
    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return uid


async def get_subscription_status(user_id: str) -> dict | None:
    """Get active subscription for a user."""
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM get_subscription($1)", user_id
        )
        if not row:
            return None
        return dict(row)


async def get_current_usage(user_id: str, period_start: datetime, period_end: datetime) -> dict:
    """Get or create usage period and return current counts."""
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM get_usage_period($1, $2, $3)",
            user_id, period_start, period_end,
        )
        if not row:
            return {
                "report_count": 0,
                "deep_analysis_count": 0,
                "batch_count": 0,
                "letter_count": 0,
                "comparison_count": 0,
            }
        return dict(row)


async def increment_usage(user_id: str, feature: str) -> None:
    """Atomically increment a usage counter."""
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("SELECT increment_usage($1, $2)", user_id, feature)


async def get_tier_limits(tier: str) -> dict | None:
    """Get limits for a tier."""
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM get_tier_limits($1)", tier)
        if not row:
            return None
        return dict(row)


async def get_all_tier_limits() -> list[dict]:
    """Get all tiers with limits, ordered by sort_order."""
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM tier_limits ORDER BY sort_order"
        )
        return [dict(r) for r in rows]


async def is_payments_enabled() -> bool:
    """Check if payments are enabled in billing_config."""
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value FROM billing_config WHERE key = 'payments_enabled'"
        )
        return row is not None and row["value"].lower() == "true"


async def get_billing_config() -> dict[str, str]:
    """Get all billing config as a dict."""
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM get_billing_config()")
        return {r["key"]: r["value"] for r in rows}


async def check_billing_override(user_id: str) -> dict | None:
    """Check if user has billing overrides."""
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM check_user_billing_override($1)", user_id
        )
        if not row:
            return None
        return dict(row)


async def update_billing_config(key: str, value: str) -> None:
    """Update a billing config value."""
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO billing_config (key, value, updated_at) VALUES ($1, $2, NOW()) "
            "ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()",
            key, value,
        )


async def set_user_override(user_id: str, overrides: dict, admin_id: str) -> None:
    """Set billing overrides for a user."""
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO user_billing_overrides
               (user_id, payments_exempt, custom_trial_days, custom_tier, notes, updated_at, updated_by)
               VALUES ($1, $2, $3, $4, $5, NOW(), $6)
               ON CONFLICT (user_id) DO UPDATE SET
                   payments_exempt = EXCLUDED.payments_exempt,
                   custom_trial_days = EXCLUDED.custom_trial_days,
                   custom_tier = EXCLUDED.custom_tier,
                   notes = EXCLUDED.notes,
                   updated_at = NOW(),
                   updated_by = EXCLUDED.updated_by""",
            user_id,
            overrides.get("payments_exempt", False),
            overrides.get("custom_trial_days"),
            overrides.get("custom_tier"),
            overrides.get("notes"),
            admin_id,
        )


async def list_user_overrides() -> list[dict]:
    """List all user billing overrides."""
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM user_billing_overrides ORDER BY updated_at DESC"
        )
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Stripe customer helpers
# ---------------------------------------------------------------------------


async def _get_or_create_stripe_customer(user_id: str) -> str:
    """Look up Stripe customer ID for a user, or create one in Stripe."""
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        # Check DB first
        row = await conn.fetchrow(
            "SELECT stripe_customer_id FROM customers WHERE user_id = $1::uuid",
            user_id,
        )
        if row:
            return row["stripe_customer_id"]

        # Get user email for Stripe customer creation
        user_row = await conn.fetchrow(
            "SELECT email FROM users WHERE id = $1::uuid", user_id
        )
        email = user_row["email"] if user_row else None

    # Create Stripe customer
    customer = stripe.Customer.create(
        metadata={"user_id": user_id},
        **({"email": email} if email else {}),
    )

    # Save mapping in DB
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT upsert_customer($1::uuid, $2)", user_id, customer.id
        )

    return customer.id


# ---------------------------------------------------------------------------
# Admin check
# ---------------------------------------------------------------------------

_ADMIN_EMAILS: set[str] = set(
    e.strip()
    for e in os.getenv("ADMIN_EMAILS", "").split(",")
    if e.strip()
)


async def _is_admin_user(user_id: str) -> bool:
    """Check if user_id belongs to an admin."""
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT email FROM users WHERE id = $1::uuid", user_id
        )
        if not row:
            return False
        return row["email"].lower() in {e.lower() for e in _ADMIN_EMAILS}


# ---------------------------------------------------------------------------
# Billing Middleware
# ---------------------------------------------------------------------------


class BillingMiddleware(BaseHTTPMiddleware):
    """Enforce subscription limits on metered endpoints.

    Only active when REQUIRE_AUTH=true (web mode).
    """

    async def dispatch(self, request: Request, call_next):
        # Skip for non-metered paths and OPTIONS
        path = request.url.path
        if request.method == "OPTIONS" or any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        # Only meter paths in the feature map
        counter = _FEATURE_MAP.get(path)
        if not counter:
            return await call_next(request)

        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            return await call_next(request)

        try:
            # Check if payments are enabled
            if not await is_payments_enabled():
                return await call_next(request)

            # Check user-level override
            override = await check_billing_override(user_id)
            if override and override.get("payments_exempt"):
                return await call_next(request)

            # Get subscription
            sub = await get_subscription_status(user_id)
            if not sub:
                return JSONResponse(
                    status_code=402,
                    content={
                        "detail": "No active subscription. Start a free trial or subscribe to continue.",
                        "tier": None,
                        "feature": _FEATURE_DISPLAY.get(counter, counter),
                        "limit": 0,
                        "used": 0,
                        "upgrade_url": "/billing",
                    },
                )

            # Get tier (use override custom_tier if set)
            tier = sub["tier"]
            if override and override.get("custom_tier"):
                tier = override["custom_tier"]

            # Get limits for the tier
            limits = await get_tier_limits(tier)
            if not limits:
                return await call_next(request)

            # Check the specific limit
            limit_key = _LIMIT_MAP.get(counter)
            if not limit_key:
                return await call_next(request)

            max_allowed = limits.get(limit_key)
            if max_allowed is None:
                # NULL = unlimited
                await increment_usage(user_id, counter)
                return await call_next(request)

            # Get current usage
            period_start = sub.get("current_period_start") or datetime.now(timezone.utc).replace(day=1)
            period_end = sub.get("current_period_end") or datetime.now(timezone.utc)
            usage = await get_current_usage(user_id, period_start, period_end)
            current_count = usage.get(counter, 0)

            if current_count >= max_allowed:
                return JSONResponse(
                    status_code=402,
                    content={
                        "detail": "Usage limit reached",
                        "tier": tier,
                        "feature": _FEATURE_DISPLAY.get(counter, counter),
                        "limit": max_allowed,
                        "used": current_count,
                        "upgrade_url": "/billing",
                    },
                )

            # Within limits — increment and proceed
            await increment_usage(user_id, counter)
            return await call_next(request)

        except Exception:
            logger.exception("Billing middleware error for user %s", user_id)
            # On error, allow the request through rather than blocking
            return await call_next(request)


# ---------------------------------------------------------------------------
# Billing API Router
# ---------------------------------------------------------------------------

billing_router = APIRouter(prefix="/billing", tags=["billing"])


@billing_router.get("/status")
async def billing_status(request: Request):
    """Get current subscription status, usage, and limits."""
    user_id = _get_user_id(request)

    payments_on = await is_payments_enabled()
    sub = await get_subscription_status(user_id)
    override = await check_billing_override(user_id)
    config = await get_billing_config()

    # Determine effective tier
    tier = None
    if sub:
        tier = sub["tier"]
    if override and override.get("custom_tier"):
        tier = override["custom_tier"]

    # Default to trial tier if no subscription
    if not tier:
        tier = config.get("trial_tier", "professional")

    limits = await get_tier_limits(tier)

    # Get usage for current period
    usage = {
        "report_count": 0,
        "deep_analysis_count": 0,
        "batch_count": 0,
        "letter_count": 0,
        "comparison_count": 0,
    }
    if sub and sub.get("current_period_start") and sub.get("current_period_end"):
        usage = await get_current_usage(
            user_id, sub["current_period_start"], sub["current_period_end"]
        )

    return {
        "subscription": {
            "has_subscription": sub is not None,
            "tier": tier,
            "status": sub["status"] if sub else None,
            "trial_end": sub["trial_end"].isoformat() if sub and sub.get("trial_end") else None,
            "current_period_end": sub["current_period_end"].isoformat() if sub and sub.get("current_period_end") else None,
            "cancel_at_period_end": sub["cancel_at_period_end"] if sub else False,
            "discount": {
                "name": sub["discount_name"],
                "percent": sub["discount_percent"],
                "months_remaining": sub["discount_months_remaining"],
            } if sub and sub.get("discount_name") else None,
        },
        "usage": usage,
        "limits": limits,
        "payments_enabled": payments_on,
    }


@billing_router.get("/prices")
async def billing_prices():
    """Get available tiers with prices."""
    tiers = await get_all_tier_limits()
    return tiers


@billing_router.post("/create-checkout")
async def create_checkout(request: Request):
    """Create a Stripe Checkout session for the requested tier."""
    user_id = _get_user_id(request)
    body = await request.json()
    tier = body.get("tier", "starter")
    interval = body.get("interval", "monthly")

    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured.")

    tier_prices = _TIER_TO_PRICES.get(tier)
    if not tier_prices:
        raise HTTPException(status_code=400, detail=f"Unknown tier: {tier}")

    price_id = tier_prices.get(interval)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Unknown interval: {interval}")

    # Get or create Stripe customer
    customer_id = await _get_or_create_stripe_customer(user_id)

    # Get trial days from config
    config = await get_billing_config()
    trial_days = int(config.get("trial_period_days", "14"))

    # Check if user already had a subscription (no trial for returning users)
    existing_sub = await get_subscription_status(user_id)
    if existing_sub:
        trial_days = 0

    success_url = body.get("success_url", "")
    cancel_url = body.get("cancel_url", "")

    session_params: dict = {
        "customer": customer_id,
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "metadata": {"user_id": user_id, "tier": tier},
        "allow_promotion_codes": True,
    }

    if success_url:
        session_params["success_url"] = success_url
    if cancel_url:
        session_params["cancel_url"] = cancel_url
    if trial_days > 0:
        session_params["subscription_data"] = {
            "trial_period_days": trial_days,
            "metadata": {"user_id": user_id, "tier": tier},
        }

    session = stripe.checkout.Session.create(**session_params)
    return {"url": session.url}


@billing_router.post("/create-portal")
async def create_portal(request: Request):
    """Create a Stripe Billing Portal session."""
    user_id = _get_user_id(request)
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}

    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured.")

    customer_id = await _get_or_create_stripe_customer(user_id)

    portal_params: dict = {"customer": customer_id}
    return_url = body.get("return_url")
    if return_url:
        portal_params["return_url"] = return_url

    session = stripe.billing_portal.Session.create(**portal_params)
    return {"url": session.url}


@billing_router.post("/cancel")
async def cancel_subscription(request: Request):
    """Cancel subscription at period end and record the reason."""
    user_id = _get_user_id(request)
    body = await request.json()

    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured.")

    sub = await get_subscription_status(user_id)
    if not sub:
        raise HTTPException(status_code=400, detail="No active subscription to cancel.")

    # Record cancellation reason in DB
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT record_cancellation($1, $2, $3, $4)",
            user_id, sub["id"],
            body.get("reason", ""),
            body.get("reason_detail", ""),
        )

    # Cancel at period end via Stripe
    stripe.Subscription.modify(
        sub["id"],
        cancel_at_period_end=True,
    )

    return {"canceled": True, "cancel_at_period_end": True}


# ---------------------------------------------------------------------------
# Stripe Webhook Handler
# ---------------------------------------------------------------------------

webhook_router = APIRouter(tags=["billing-webhook"])


@webhook_router.post("/billing/webhook")
async def stripe_webhook(request: Request):
    """Handle incoming Stripe webhook events.

    This endpoint does NOT require auth — Stripe calls it directly.
    Verification is done via the webhook signature.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Webhook secret not configured.")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload.")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature.")

    event_type = event["type"]
    data_object = event["data"]["object"]

    logger.info("Stripe webhook received: %s", event_type)

    try:
        if event_type == "checkout.session.completed":
            await _handle_checkout_completed(data_object)

        elif event_type in (
            "customer.subscription.created",
            "customer.subscription.updated",
        ):
            await _handle_subscription_upsert(data_object)

        elif event_type == "customer.subscription.deleted":
            await _handle_subscription_deleted(data_object)

        elif event_type == "invoice.payment_succeeded":
            await _handle_invoice_paid(data_object)

        elif event_type == "invoice.payment_failed":
            await _handle_invoice_failed(data_object)

        else:
            logger.debug("Unhandled webhook event type: %s", event_type)

    except Exception:
        logger.exception("Error processing webhook %s", event_type)
        # Return 200 so Stripe doesn't retry on application errors
        # (retries should only happen for 5xx / network errors)

    return {"received": True}


async def _resolve_user_id_from_customer(customer_id: str) -> str | None:
    """Look up user_id from Stripe customer_id in our DB."""
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id FROM customers WHERE stripe_customer_id = $1",
            customer_id,
        )
        return str(row["user_id"]) if row else None


async def _handle_checkout_completed(session: dict) -> None:
    """Handle checkout.session.completed — link customer, create subscription."""
    customer_id = session.get("customer")
    user_id = (session.get("metadata") or {}).get("user_id")
    subscription_id = session.get("subscription")

    if not user_id or not customer_id:
        logger.warning("checkout.session.completed missing user_id or customer")
        return

    # Save customer mapping
    from storage.pg_database import _get_pool

    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT upsert_customer($1::uuid, $2)", user_id, customer_id
        )

    # Fetch full subscription from Stripe and upsert
    if subscription_id:
        sub = stripe.Subscription.retrieve(subscription_id)
        await _upsert_subscription_from_stripe(sub, user_id)


async def _handle_subscription_upsert(sub_obj: dict) -> None:
    """Handle subscription created/updated."""
    customer_id = sub_obj.get("customer")
    user_id = (sub_obj.get("metadata") or {}).get("user_id")

    if not user_id:
        user_id = await _resolve_user_id_from_customer(customer_id)

    if not user_id:
        logger.warning("Cannot resolve user_id for subscription %s", sub_obj.get("id"))
        return

    await _upsert_subscription_from_stripe(sub_obj, user_id)


async def _handle_subscription_deleted(sub_obj: dict) -> None:
    """Handle subscription deleted — mark as canceled."""
    await _handle_subscription_upsert(sub_obj)


async def _handle_invoice_paid(invoice: dict) -> None:
    """Handle successful payment — reset usage period for new billing cycle."""
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return

    customer_id = invoice.get("customer")
    user_id = await _resolve_user_id_from_customer(customer_id)
    if not user_id:
        return

    logger.info("Invoice paid for user %s, subscription %s", user_id, subscription_id)


async def _handle_invoice_failed(invoice: dict) -> None:
    """Handle failed payment — update subscription status."""
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return

    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        customer_id = sub.get("customer") if isinstance(sub, dict) else sub.customer
        user_id = await _resolve_user_id_from_customer(
            customer_id if isinstance(customer_id, str) else str(customer_id)
        )
        if user_id:
            await _upsert_subscription_from_stripe(sub, user_id)
    except Exception:
        logger.exception("Error handling invoice.payment_failed for sub %s", subscription_id)


async def _upsert_subscription_from_stripe(sub_obj, user_id: str) -> None:
    """Upsert subscription row from a Stripe Subscription object/dict."""
    from storage.pg_database import _get_pool

    # Handle both dict and Stripe object access
    def _get(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    sub_id = _get(sub_obj, "id")
    status = _get(sub_obj, "status")
    cancel_at_period_end = _get(sub_obj, "cancel_at_period_end", False)

    # Get price and tier from the first line item
    items = _get(sub_obj, "items")
    price_id = None
    tier = None
    if items:
        item_data = items.get("data", []) if isinstance(items, dict) else getattr(items, "data", [])
        if item_data:
            first_item = item_data[0]
            price_obj = first_item.get("price") if isinstance(first_item, dict) else getattr(first_item, "price", None)
            if price_obj:
                price_id = price_obj.get("id") if isinstance(price_obj, dict) else getattr(price_obj, "id", None)

    if price_id:
        tier = _PRICE_TO_TIER.get(price_id)

    # Fall back to metadata tier
    if not tier:
        metadata = _get(sub_obj, "metadata") or {}
        tier = metadata.get("tier") if isinstance(metadata, dict) else getattr(metadata, "tier", None)

    # Timestamps (Stripe sends as Unix epoch seconds)
    def _ts(val):
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return datetime.fromtimestamp(val, tz=timezone.utc)
        return val

    current_period_start = _ts(_get(sub_obj, "current_period_start"))
    current_period_end = _ts(_get(sub_obj, "current_period_end"))
    trial_start = _ts(_get(sub_obj, "trial_start"))
    trial_end = _ts(_get(sub_obj, "trial_end"))
    canceled_at = _ts(_get(sub_obj, "canceled_at"))
    ended_at = _ts(_get(sub_obj, "ended_at"))

    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """SELECT upsert_subscription(
                $1, $2::uuid, $3, $4, $5,
                $6, $7, $8, $9, $10, $11, $12
            )""",
            sub_id, user_id, price_id, status, tier,
            current_period_start, current_period_end,
            trial_start, trial_end,
            cancel_at_period_end, canceled_at, ended_at,
        )


# ---------------------------------------------------------------------------
# Admin billing endpoints
# ---------------------------------------------------------------------------

admin_billing_router = APIRouter(prefix="/billing/admin", tags=["billing-admin"])


async def _require_admin(request: Request) -> str:
    """Check admin access and return user_id."""
    user_id = _get_user_id(request)
    if not await _is_admin_user(user_id):
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user_id


@admin_billing_router.get("/config")
async def get_admin_config(request: Request):
    """Get all billing configuration."""
    await _require_admin(request)
    config = await get_billing_config()
    return config


@admin_billing_router.put("/config")
async def update_admin_config(request: Request):
    """Update a billing config key/value."""
    await _require_admin(request)
    body = await request.json()
    key = body.get("key")
    value = body.get("value")
    if not key or value is None:
        raise HTTPException(status_code=400, detail="key and value required.")

    allowed_keys = {
        "payments_enabled", "trial_period_days", "trial_tier",
        "grace_period_hours", "require_payment_method_for_trial",
        "retention_coupon_id", "retention_offer_text",
    }
    if key not in allowed_keys:
        raise HTTPException(status_code=400, detail=f"Unknown config key: {key}")

    await update_billing_config(key, str(value))
    return {"key": key, "value": str(value)}


@admin_billing_router.get("/overrides")
async def get_admin_overrides(request: Request):
    """List all user billing overrides."""
    await _require_admin(request)
    overrides = await list_user_overrides()
    # Convert datetime/uuid to strings
    result = []
    for o in overrides:
        entry = {}
        for k, v in o.items():
            if isinstance(v, datetime):
                entry[k] = v.isoformat()
            elif hasattr(v, "hex"):  # UUID
                entry[k] = str(v)
            else:
                entry[k] = v
        result.append(entry)
    return result


@admin_billing_router.put("/overrides/{target_user_id}")
async def set_admin_override(target_user_id: str, request: Request):
    """Set billing overrides for a specific user."""
    admin_id = await _require_admin(request)
    body = await request.json()
    await set_user_override(target_user_id, body, admin_id)
    return {"updated": True, "user_id": target_user_id}
