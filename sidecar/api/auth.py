"""JWT authentication middleware for web mode.

In desktop mode (REQUIRE_AUTH not set), all requests pass through with user_id=None.
In web mode, validates Supabase JWT tokens and extracts user_id from the 'sub' claim.
"""

import os

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "").lower() == "true"
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip auth entirely in desktop mode
        if not REQUIRE_AUTH:
            request.state.user_id = None
            return await call_next(request)

        # Skip auth for health check
        if request.url.path == "/health":
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
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
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

        return await call_next(request)
