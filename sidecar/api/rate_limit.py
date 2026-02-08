"""Rate limiting for web mode using slowapi.

Limits /analyze/* endpoints to 30 requests/min per user.
Only active when REQUIRE_AUTH is set.
"""

import os

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "").lower() == "true"


def _get_user_key(request: Request) -> str:
    """Extract rate limit key from request.

    In web mode, use the authenticated user_id.
    Falls back to IP address if user_id is not available.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return user_id
    return get_remote_address(request)


# Create limiter instance
# In desktop mode, use a no-op strategy (effectively unlimited)
limiter = Limiter(
    key_func=_get_user_key,
    enabled=REQUIRE_AUTH,
    default_limits=[] if not REQUIRE_AUTH else [],
)

# Rate limit string for analyze endpoints
ANALYZE_RATE_LIMIT = "30/minute"


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom handler for rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please wait before making more requests.",
            "retry_after": exc.detail,
        },
    )
