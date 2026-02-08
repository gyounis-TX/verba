"""Audit logging middleware for web mode.

Logs every authenticated request with user_id, method, path, timestamp, and status code.
Output goes to stdout (captured by CloudWatch in production via ECS).
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("audit")
logger.setLevel(logging.INFO)

# Ensure we have a stream handler (stdout) if not already configured
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)


class AuditMiddleware(BaseHTTPMiddleware):
    """Log every authenticated request for compliance and debugging."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 1)

        user_id = getattr(request.state, "user_id", None) or "anonymous"
        method = request.method
        path = request.url.path
        status_code = response.status_code

        logger.info(
            "user=%s method=%s path=%s status=%d duration_ms=%.1f",
            user_id,
            method,
            path,
            status_code,
            duration_ms,
        )

        return response
