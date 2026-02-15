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
                    {"detail": f"Internal server error: {type(exc).__name__}: {exc}"},
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
                {"detail": f"Invalid token: {e}"}, status_code=401
            )

        # Auto-provision user in the database on first request
        try:
            await _ensure_user_exists(
                request.state.user_id,
                payload.get("email", ""),
            )
        except Exception:
            _logger.exception("Failed to auto-provision user %s", request.state.user_id)

        try:
            return await call_next(request)
        except Exception as exc:
            _logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            return JSONResponse(
                {"detail": f"Internal server error: {type(exc).__name__}: {exc}"},
                status_code=500,
            )
