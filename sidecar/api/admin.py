"""Admin endpoints: usage summaries and user management.

Web-only (REQUIRE_AUTH) — requires a valid JWT and admin privileges.
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Query, Request

logger = logging.getLogger(__name__)

REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "").lower() == "true"
_ADMIN_EMAILS = set(
    e.strip()
    for e in os.getenv("ADMIN_EMAILS", "").split(",")
    if e.strip()
)


router = APIRouter(prefix="/admin", tags=["admin"])


async def _require_admin(request: Request) -> str:
    """Extract user_id and verify admin access. Raises 403 if not admin."""
    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if not _ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="No admin users configured.")
    # Look up user's email from the database and check against admin list
    from storage.pg_database import _get_pool
    pool = await _get_pool()
    row = await pool.fetchrow("SELECT email FROM users WHERE id = $1::uuid", uid)
    if not row or row["email"].lower() not in {e.lower() for e in _ADMIN_EMAILS}:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return uid


@router.get("/usage")
async def admin_usage_summary(request: Request, since: str = Query(...)):
    """Return usage summary for all users since a given date."""
    if not REQUIRE_AUTH:
        raise HTTPException(status_code=404, detail="Not available in desktop mode.")

    await _require_admin(request)

    from storage.pg_database import _get_pool
    pool = await _get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM admin_usage_summary($1::TIMESTAMPTZ)",
            since,
        )

    return [dict(row) for row in rows]


@router.get("/users")
async def admin_list_users(request: Request):
    """Return list of all registered users."""
    if not REQUIRE_AUTH:
        raise HTTPException(status_code=404, detail="Not available in desktop mode.")

    await _require_admin(request)

    from storage.pg_database import _get_pool
    pool = await _get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM admin_list_users()")

    return [dict(row) for row in rows]


@router.post("/usage/log")
async def log_usage(request: Request):
    """Log a usage entry (model, tokens, request type)."""
    if not REQUIRE_AUTH:
        return {"ok": True}

    uid = getattr(request.state, "user_id", None)
    if not uid:
        return {"ok": True}  # Silently skip if no user

    try:
        body = await request.json()
    except Exception:
        return {"ok": True}

    from storage.pg_database import _get_pool
    pool = await _get_pool()

    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO usage_log (user_id, model_used, input_tokens, output_tokens, request_type, deep_analysis)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            uid,
            body.get("model_used", ""),
            body.get("input_tokens", 0),
            body.get("output_tokens", 0),
            body.get("request_type", "explain"),
            body.get("deep_analysis", False),
        )

    return {"ok": True}
