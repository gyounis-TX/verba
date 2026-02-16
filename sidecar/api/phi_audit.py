"""PHI access audit logging for HIPAA §164.312(b) compliance.

Logs WHO accessed WHAT patient data WHEN to a persistent database table.
All calls are fire-and-forget — failures are logged but never break request flow.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

logger = logging.getLogger(__name__)


async def log_phi_access(
    request: "Request",
    action: str,
    resource_type: str,
    resource_id: str | None = None,
) -> None:
    """Insert a PHI access audit log entry (fire-and-forget).

    Args:
        request: The FastAPI request (used to extract user_id, IP, User-Agent).
        action: What was done — e.g. 'view_report', 'delete_report', 'export_account'.
        resource_type: Kind of resource — 'history', 'letter', 'account'.
        resource_id: The sync_id of the accessed record, or None for bulk ops.
    """
    try:
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            return

        # Client IP: prefer X-Forwarded-For (behind ALB/proxy), else direct
        ip_address = request.headers.get("x-forwarded-for")
        if ip_address:
            ip_address = ip_address.split(",")[0].strip()
        elif request.client:
            ip_address = request.client.host
        else:
            ip_address = None

        user_agent = request.headers.get("user-agent")

        from storage.pg_database import _get_pool

        pool = await _get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO phi_access_log
                   (user_id, action, resource_type, resource_id, ip_address, user_agent)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                user_id,
                action,
                resource_type,
                resource_id,
                ip_address,
                user_agent,
            )
    except Exception:
        logger.exception("Failed to write PHI access audit log")
