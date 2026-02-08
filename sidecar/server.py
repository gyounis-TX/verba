import os
import socket

import uvicorn

REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "").lower() == "true"


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(app, port: int):
    # In web mode, bind to all interfaces; in desktop mode, localhost only
    host = "0.0.0.0" if REQUIRE_AUTH else "127.0.0.1"
    print(f"PORT:{port}", flush=True)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="warning",
    )
