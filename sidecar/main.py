from fastapi import FastAPI

from api.middleware import add_cors_middleware
from api.routes import router
from server import find_free_port, start_server
from storage import get_db, get_keychain


def create_app() -> FastAPI:
    app = FastAPI(title="Verba Sidecar", version="0.2.0")
    add_cors_middleware(app)
    app.include_router(router)

    @app.on_event("startup")
    async def _init_storage() -> None:
        get_db()
        get_keychain()

    return app


if __name__ == "__main__":
    port = find_free_port()
    app = create_app()
    start_server(app, port)
