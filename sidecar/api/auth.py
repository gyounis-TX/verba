"""JWT authentication middleware for web mode.

In desktop mode (REQUIRE_AUTH not set), all requests pass through with user_id=None.
In web mode, validates Supabase JWT tokens and extracts user_id from the 'sub' claim.
Supports both HS256 (legacy) and RS256 (modern Supabase) signing algorithms.
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
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

# Cache for JWKS clients keyed by issuer URL
_jwks_clients: dict[str, PyJWKClient] = {}


def _get_jwks_client(issuer: str) -> PyJWKClient:
    """Get or create a cached PyJWKClient for the given issuer."""
    if issuer not in _jwks_clients:
        jwks_url = f"{issuer}/.well-known/jwks.json"
        _jwks_clients[issuer] = PyJWKClient(jwks_url)
    return _jwks_clients[issuer]


def _decode_token(token: str) -> dict:
    """Decode a Supabase JWT, supporting both HS256 and RS256."""
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "HS256")

    if alg == "HS256":
        return jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )

    # RS256 or other asymmetric algorithm — fetch public key from JWKS
    unverified = jwt.decode(token, options={"verify_signature": False})
    issuer = unverified.get("iss", "")
    if not issuer:
        raise jwt.InvalidTokenError("Token missing iss claim for JWKS lookup")

    jwks_client = _get_jwks_client(issuer)
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=[alg],
        audience="authenticated",
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

        # Skip auth for health check and CORS preflight
        if request.url.path == "/health" or request.method == "OPTIONS":
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

        try:
            return await call_next(request)
        except Exception as exc:
            _logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            return JSONResponse(
                {"detail": f"Internal server error: {type(exc).__name__}: {exc}"},
                status_code=500,
            )
