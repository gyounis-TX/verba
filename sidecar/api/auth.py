"""JWT authentication middleware for web mode.

In desktop mode (REQUIRE_AUTH not set), all requests pass through with user_id=None.
In web mode, validates Cognito JWT tokens and extracts user_id from the 'sub' claim.
"""

import logging
import os

import jwt
from jwt import PyJWKClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_logger = logging.getLogger(__name__)

REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "").lower() == "true"
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
COGNITO_REGION = os.getenv("AWS_REGION", "us-east-1")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID", "")

if REQUIRE_AUTH:
    if not COGNITO_USER_POOL_ID:
        raise ValueError("COGNITO_USER_POOL_ID must be set when REQUIRE_AUTH=true")
    if not COGNITO_CLIENT_ID:
        raise ValueError("COGNITO_CLIENT_ID must be set when REQUIRE_AUTH=true")

# Computed from pool ID
_COGNITO_ISSUER = (
    f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
    if COGNITO_USER_POOL_ID
    else ""
)

# Cache for JWKS client
_jwks_client: PyJWKClient | None = None

# Track which user IDs have been provisioned this process lifetime
_provisioned_users: set[str] = set()

# Cache practice context per user_id to avoid DB query per request.
# Entries expire after _PRACTICE_CACHE_TTL seconds to prevent stale authorization.
import time as _time

_PRACTICE_CACHE_TTL = 30  # 30 seconds
_practice_cache: dict[str, tuple[float, dict | None]] = {}


async def _attach_practice_context(request) -> None:
    """Attach practice_id, practice_role, practice_sharing to request.state.

    Uses a per-process cache keyed by user_id. Cache entries are invalidated
    by practice.py when membership or settings change.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        request.state.practice_id = None
        request.state.practice_role = None
        request.state.practice_sharing = None
        return

    if user_id in _practice_cache:
        ts, cached = _practice_cache[user_id]
        if _time.time() - ts > _PRACTICE_CACHE_TTL:
            del _practice_cache[user_id]
        elif cached is None:
            request.state.practice_id = None
            request.state.practice_role = None
            request.state.practice_sharing = None
            return
        else:
            request.state.practice_id = cached["practice_id"]
            request.state.practice_role = cached["practice_role"]
            request.state.practice_sharing = cached["practice_sharing"]
            return

    try:
        from storage.pg_database import _get_pool
        pool = await _get_pool()
        row = await pool.fetchrow(
            "SELECT pm.practice_id, pm.role, p.sharing_enabled "
            "FROM practice_members pm JOIN practices p ON p.id = pm.practice_id "
            "WHERE pm.user_id = $1::uuid", user_id,
        )
        if row:
            ctx = {
                "practice_id": str(row["practice_id"]),
                "practice_role": row["role"],
                "practice_sharing": row["sharing_enabled"],
            }
            _practice_cache[user_id] = (_time.time(), ctx)
            request.state.practice_id = ctx["practice_id"]
            request.state.practice_role = ctx["practice_role"]
            request.state.practice_sharing = ctx["practice_sharing"]
        else:
            _practice_cache[user_id] = (_time.time(), None)
            request.state.practice_id = None
            request.state.practice_role = None
            request.state.practice_sharing = None
    except Exception:
        _logger.exception("Failed to load practice context for user %s", user_id)
        request.state.practice_id = None
        request.state.practice_role = None
        request.state.practice_sharing = None


def invalidate_practice_cache(user_id: str) -> None:
    """Remove a user's practice context from cache.

    Called by practice.py when membership or settings change.
    """
    _practice_cache.pop(user_id, None)


async def _ensure_user_exists(user_id: str, email: str) -> None:
    """Upsert user into the database on first authenticated request."""
    if user_id in _provisioned_users:
        return
    try:
        from storage.pg_database import _get_pool
        pool = await _get_pool()
        await pool.execute(
            """INSERT INTO users (id, email, last_sign_in_at)
               VALUES ($1::uuid, $2, NOW())
               ON CONFLICT (id) DO UPDATE SET last_sign_in_at = NOW()""",
            user_id, email,
        )
        _provisioned_users.add(user_id)
    except Exception:
        raise


def _get_jwks_client() -> PyJWKClient:
    """Get or create the cached JWKS client for Cognito."""
    global _jwks_client
    if _jwks_client is None:
        jwks_url = f"{_COGNITO_ISSUER}/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_url)
    return _jwks_client


def _decode_token(token: str) -> dict:
    """Decode a Cognito JWT using RS256 + JWKS."""
    jwks_client = _get_jwks_client()
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=_COGNITO_ISSUER,
        audience=COGNITO_CLIENT_ID,
    )


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip auth entirely in desktop mode
        if not REQUIRE_AUTH:
            request.state.user_id = None
            try:
                return await call_next(request)
            except Exception as exc:
                _logger.exception("Unhandled error on %s %s", request.method, request.url.path)
                return JSONResponse(
                    {"detail": "Internal server error"},
                    status_code=500,
                )

        # Skip auth for health check, CORS preflight, and Stripe webhook
        if request.url.path in ("/health", "/billing/webhook") or request.method == "OPTIONS":
            request.state.user_id = None
            return await call_next(request)

        # Extract and verify JWT
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"detail": "Missing authorization header"}, status_code=401
            )

        token = auth_header[7:]
        try:
            payload = _decode_token(token)
            request.state.user_id = payload.get("sub")
            if not request.state.user_id:
                return JSONResponse(
                    {"detail": "Invalid token: missing sub"}, status_code=401
                )
        except jwt.ExpiredSignatureError:
            return JSONResponse({"detail": "Token expired"}, status_code=401)
        except jwt.InvalidTokenError as e:
            return JSONResponse(
                {"detail": "Invalid token"}, status_code=401
            )

        # Auto-provision user in the database on first request
        try:
            await _ensure_user_exists(
                request.state.user_id,
                payload.get("email", ""),
            )
        except Exception:
            _logger.exception("Failed to auto-provision user %s", request.state.user_id)

        # Attach practice context to request state
        await _attach_practice_context(request)

        try:
            return await call_next(request)
        except Exception as exc:
            _logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            return JSONResponse(
                {"detail": "Internal server error"},
                status_code=500,
            )
