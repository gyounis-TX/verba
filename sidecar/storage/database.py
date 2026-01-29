"""SQLite database for settings and analysis history."""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

import platformdirs

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    test_type TEXT NOT NULL,
    test_type_display TEXT NOT NULL,
    filename TEXT,
    summary TEXT NOT NULL,
    full_response TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(created_at);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    test_type TEXT,
    tone TEXT,
    structure_instructions TEXT,
    closing_text TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
"""


def _get_db_path() -> str:
    """Return OS-appropriate path for verba.db."""
    data_dir = platformdirs.user_data_dir("Verba")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "verba.db")


class Database:
    """SQLite-backed storage for settings and history."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _get_db_path()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    # --- Settings ---

    def get_setting(self, key: str) -> str | None:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None
        finally:
            conn.close()

    def set_setting(self, key: str, value: str) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()

    def get_all_settings(self) -> dict[str, str]:
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            return {row["key"]: row["value"] for row in rows}
        finally:
            conn.close()

    def delete_setting(self, key: str) -> None:
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()
        finally:
            conn.close()

    # --- History ---

    def save_history(
        self,
        test_type: str,
        test_type_display: str,
        summary: str,
        full_response: dict[str, Any],
        filename: str | None = None,
    ) -> int:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """INSERT INTO history (test_type, test_type_display, filename, summary, full_response)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    test_type,
                    test_type_display,
                    filename,
                    summary,
                    json.dumps(full_response),
                ),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]
        finally:
            conn.close()

    def list_history(
        self,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        conn = self._get_conn()
        try:
            if search:
                like = f"%{search}%"
                count_row = conn.execute(
                    """SELECT COUNT(*) as cnt FROM history
                       WHERE summary LIKE ? OR test_type_display LIKE ? OR filename LIKE ?""",
                    (like, like, like),
                ).fetchone()
                total = count_row["cnt"]
                rows = conn.execute(
                    """SELECT id, created_at, test_type, test_type_display, filename, summary
                       FROM history
                       WHERE summary LIKE ? OR test_type_display LIKE ? OR filename LIKE ?
                       ORDER BY created_at DESC
                       LIMIT ? OFFSET ?""",
                    (like, like, like, limit, offset),
                ).fetchall()
            else:
                count_row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM history"
                ).fetchone()
                total = count_row["cnt"]
                rows = conn.execute(
                    """SELECT id, created_at, test_type, test_type_display, filename, summary
                       FROM history
                       ORDER BY created_at DESC
                       LIMIT ? OFFSET ?""",
                    (limit, offset),
                ).fetchall()
            return [dict(row) for row in rows], total
        finally:
            conn.close()

    def get_history(self, history_id: int) -> dict[str, Any] | None:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM history WHERE id = ?", (history_id,)
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            result["full_response"] = json.loads(result["full_response"])
            return result
        finally:
            conn.close()

    def delete_history(self, history_id: int) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM history WHERE id = ?", (history_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


    # --- Templates ---

    def create_template(
        self,
        name: str,
        test_type: str | None = None,
        tone: str | None = None,
        structure_instructions: str | None = None,
        closing_text: str | None = None,
    ) -> dict[str, Any]:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """INSERT INTO templates (name, test_type, tone, structure_instructions, closing_text)
                   VALUES (?, ?, ?, ?, ?)""",
                (name, test_type, tone, structure_instructions, closing_text),
            )
            conn.commit()
            return self.get_template(cursor.lastrowid)  # type: ignore[return-value]
        finally:
            conn.close()

    def list_templates(self) -> tuple[list[dict[str, Any]], int]:
        conn = self._get_conn()
        try:
            count_row = conn.execute("SELECT COUNT(*) as cnt FROM templates").fetchone()
            total = count_row["cnt"]
            rows = conn.execute(
                "SELECT * FROM templates ORDER BY created_at DESC"
            ).fetchall()
            return [dict(row) for row in rows], total
        finally:
            conn.close()

    def get_template(self, template_id: int) -> dict[str, Any] | None:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM templates WHERE id = ?", (template_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_template(self, template_id: int, **kwargs: Any) -> dict[str, Any] | None:
        conn = self._get_conn()
        try:
            existing = conn.execute(
                "SELECT * FROM templates WHERE id = ?", (template_id,)
            ).fetchone()
            if not existing:
                return None

            allowed = {"name", "test_type", "tone", "structure_instructions", "closing_text"}
            updates = {k: v for k, v in kwargs.items() if k in allowed}
            if not updates:
                return dict(existing)

            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values())
            values.append(template_id)
            conn.execute(
                f"UPDATE templates SET {set_clause}, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
                values,
            )
            conn.commit()
            return self.get_template(template_id)
        finally:
            conn.close()

    def delete_template(self, template_id: int) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM templates WHERE id = ?", (template_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


_db_instance: Database | None = None


def get_db() -> Database:
    """Return the module-level Database singleton."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance
