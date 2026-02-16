"""BAA (Business Associate Agreement) acceptance endpoints.

Web-only (REQUIRE_AUTH) — these endpoints need a valid JWT.
Tracks user acceptance of the BAA with version, IP, and user-agent
for HIPAA compliance record-keeping.
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

BAA_VERSION = "1.0"

router = APIRouter(prefix="/baa", tags=["baa"])


def _get_user_id(request: Request) -> str:
    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return uid


async def _get_pool():
    from storage.pg_database import _get_pool
    return await _get_pool()


@router.get("/status")
async def get_baa_status(request: Request):
    """Check whether the user has accepted the current BAA version."""
    user_id = _get_user_id(request)
    pool = await _get_pool()
    row = await pool.fetchrow(
        "SELECT id FROM baa_acceptances WHERE user_id = $1::uuid AND baa_version = $2 LIMIT 1",
        user_id,
        BAA_VERSION,
    )
    return {"accepted": row is not None, "version": BAA_VERSION}


@router.post("/accept")
async def accept_baa(request: Request):
    """Record the user's acceptance of the current BAA version."""
    user_id = _get_user_id(request)
    ip_address = request.headers.get("x-forwarded-for")
    if ip_address:
        ip_address = ip_address.split(",")[0].strip()
    elif request.client:
        ip_address = request.client.host
    else:
        ip_address = None
    user_agent = request.headers.get("user-agent", "")

    pool = await _get_pool()
    await pool.execute(
        """INSERT INTO baa_acceptances (user_id, baa_version, ip_address, user_agent)
           VALUES ($1::uuid, $2, $3, $4)""",
        user_id,
        BAA_VERSION,
        ip_address,
        user_agent,
    )
    logger.info("BAA v%s accepted by user %s", BAA_VERSION, user_id)
    return {"accepted": True}
