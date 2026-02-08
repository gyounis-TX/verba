import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.auth import AuthMiddleware, REQUIRE_AUTH
from api.middleware import add_cors_middleware
from api.routes import router
from server import find_free_port, start_server
from storage import get_db, get_keychain

_USE_PG = bool(os.getenv("DATABASE_URL", ""))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    if _USE_PG:
        # Initialize PostgreSQL connection pool
        from storage.pg_database import _get_pool
        await _get_pool()
    else:
        # Desktop mode: initialize SQLite and keychain
        get_db()
        get_keychain()
    yield
    # Shutdown
    if _USE_PG:
        from storage.pg_database import close_pool
        await close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="Explify Sidecar", version="0.4.0", lifespan=lifespan)
    # Auth middleware added first (inner); CORS added last (outer) so CORS
    # headers appear on all responses including auth errors.
    app.add_middleware(AuthMiddleware)
    add_cors_middleware(app)
    # Audit logging and rate limiting (web mode only)
    if REQUIRE_AUTH:
        from api.audit import AuditMiddleware
        from api.rate_limit import limiter, rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded

        app.add_middleware(AuditMiddleware)
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.include_router(router)
    return app


if __name__ == "__main__":
    port = find_free_port()
    app = create_app()
    start_server(app, port)
