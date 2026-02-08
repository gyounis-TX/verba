"""Persistent storage: database and OS keychain integration.

In web mode (DATABASE_URL set), uses PostgreSQL via PgDatabase.
In desktop mode, uses SQLite via Database + OS keychain.
"""

import os

from storage.database import Database, get_db
from storage.keychain import KeychainManager, get_keychain

_USE_PG = bool(os.getenv("DATABASE_URL", ""))


def get_active_db():
    """Return the appropriate database instance based on environment.

    - If DATABASE_URL is set: returns PgDatabase (async, PostgreSQL)
    - Otherwise: returns Database (sync, SQLite)
    """
    if _USE_PG:
        from storage.pg_database import get_pg_db
        return get_pg_db()
    return get_db()


__all__ = [
    "Database",
    "get_db",
    "KeychainManager",
    "get_keychain",
    "get_active_db",
]
