import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.auth import AuthMiddleware, REQUIRE_AUTH
from api.middleware import add_cors_middleware
from api.routes import router
from server import find_free_port, start_server
from storage import get_db, get_keychain

_logger = logging.getLogger(__name__)

_USE_PG = bool(os.getenv("DATABASE_URL", ""))
_SENTRY_DSN = os.getenv("SENTRY_DSN", "")

# PHI patterns to scrub from error reports (covers HIPAA Safe Harbor identifiers)
_PHI_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),                    # SSN
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),        # dates
    re.compile(r"\b[A-Z]{1,2}\d{6,10}\b"),                    # MRN
    re.compile(r"\b\d{10}\b"),                                 # phone
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),  # email
    re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+"),     # URLs
    re.compile(r"(?i)(?:patient|name)\s*[:=]\s*[^\n,;]{2,40}"),  # labeled patient name
    re.compile(r"(?i)(?:age[d:]?\s*)?(?:9[0-9]|1[0-4][0-9])\s*(?:-?\s*)?(?:year|yr|y/?o|y\.o\.)"),  # age>89
    re.compile(r"(?i)(?:date of (?:study|exam|service|procedure|admission|discharge|report|visit|birth))\s*[:=]?\s*[^\n]{1,30}"),  # labeled dates
]


def _scrub_phi(text: str) -> str:
    for pattern in _PHI_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _init_sentry() -> None:
    if not _SENTRY_DSN:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        def before_send(event, hint):
            # Scrub PHI from exception values
            if "exception" in event:
                for exc_info in event["exception"].get("values", []):
                    if exc_info.get("value"):
                        exc_info["value"] = _scrub_phi(exc_info["value"])
            # Scrub breadcrumbs
            for bc in event.get("breadcrumbs", {}).get("values", []):
                if bc.get("message"):
                    bc["message"] = _scrub_phi(bc["message"])
            return event

        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
            integrations=[FastApiIntegration(), StarletteIntegration()],
            before_send=before_send,
        )
    except ImportError:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    if _USE_PG:
        # Initialize PostgreSQL connection pool and run migrations
        from storage.pg_database import _get_pool, run_migrations, enforce_data_retention
        await _get_pool()
        await run_migrations()
        await enforce_data_retention()
    else:
        # Desktop mode: initialize SQLite and keychain
        get_db()
        get_keychain()

    # Load correction-based detection adjustments (both PG and SQLite)
    from test_types.registry import refresh_correction_cache
    await refresh_correction_cache()

    yield
    # Shutdown
    if _USE_PG:
        from storage.pg_database import close_pool
        await close_pool()


def create_app() -> FastAPI:
    _init_sentry()
    app = FastAPI(title="Explify Sidecar", version="1.04", lifespan=lifespan)
    # Middleware order (inner → outer): Auth → Billing → Audit → CORS
    # CORS must be outermost so ALL responses (including 500s) get headers.
    app.add_middleware(AuthMiddleware)
    if REQUIRE_AUTH:
        from api.billing import BillingMiddleware
        from api.audit import AuditMiddleware
        from api.rate_limit import limiter, rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded

        app.add_middleware(BillingMiddleware)
        app.add_middleware(AuditMiddleware)
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    add_cors_middleware(app)
    # Catch-all exception handler so unhandled errors still return JSON
    # with CORS headers (instead of a bare 500 that the browser blocks).
    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        _logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error."},
        )

    app.include_router(router)
    # Billing + account + admin management endpoints (web mode only)
    if REQUIRE_AUTH:
        from api.billing import billing_router, admin_billing_router, webhook_router
        from api.account import router as account_router
        from api.admin import router as admin_router
        from api.practice import router as practice_router
        from api.baa import router as baa_router
        app.include_router(billing_router)
        app.include_router(admin_billing_router)
        app.include_router(webhook_router)
        app.include_router(account_router)
        app.include_router(admin_router)
        app.include_router(practice_router)
        app.include_router(baa_router)
    return app


if __name__ == "__main__":
    port = find_free_port()
    app = create_app()
    start_server(app, port)
