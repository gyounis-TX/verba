"""SQLite database for settings and analysis history."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

import platformdirs


def _now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    full_response TEXT NOT NULL,
    liked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(created_at);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    test_type TEXT,
    tone TEXT,
    structure_instructions TEXT,
    closing_text TEXT,
    is_builtin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS letters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    prompt TEXT NOT NULL,
    content TEXT NOT NULL,
    letter_type TEXT NOT NULL DEFAULT 'general',
    liked INTEGER NOT NULL DEFAULT 0,
    model_used TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER
);
CREATE INDEX IF NOT EXISTS idx_letters_created_at ON letters(created_at);

CREATE TABLE IF NOT EXISTS teaching_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    test_type TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_teaching_points_test_type ON teaching_points(test_type);
"""


def _get_db_path() -> str:
    """Return OS-appropriate path for explify.db."""
    data_dir = platformdirs.user_data_dir("Explify")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "explify.db")


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
            # Migrations for existing databases
            migrations = [
                "ALTER TABLE history ADD COLUMN liked INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE history ADD COLUMN tone_preference INTEGER",
                "ALTER TABLE history ADD COLUMN detail_preference INTEGER",
                "CREATE TABLE IF NOT EXISTS teaching_points (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, test_type TEXT, created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')))",
                "ALTER TABLE templates ADD COLUMN is_builtin INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE letters ADD COLUMN liked INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE letters ADD COLUMN model_used TEXT",
                "ALTER TABLE letters ADD COLUMN input_tokens INTEGER",
                "ALTER TABLE letters ADD COLUMN output_tokens INTEGER",
                "ALTER TABLE history ADD COLUMN copied INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE history ADD COLUMN updated_at TEXT",
                "ALTER TABLE history ADD COLUMN sync_id TEXT",
                "ALTER TABLE letters ADD COLUMN updated_at TEXT",
                "ALTER TABLE letters ADD COLUMN sync_id TEXT",
                "ALTER TABLE teaching_points ADD COLUMN updated_at TEXT",
                "ALTER TABLE teaching_points ADD COLUMN sync_id TEXT",
                "ALTER TABLE settings ADD COLUMN updated_at TEXT",
                "ALTER TABLE templates ADD COLUMN sync_id TEXT",
            ]
            for migration in migrations:
                try:
                    conn.execute(migration)
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # Column already exists
            # Backfill sync_id and updated_at for existing rows
            for tbl in ("history", "letters", "teaching_points", "templates"):
                try:
                    rows = conn.execute(
                        f"SELECT id FROM {tbl} WHERE sync_id IS NULL"
                    ).fetchall()
                    for row in rows:
                        conn.execute(
                            f"UPDATE {tbl} SET sync_id = ? WHERE id = ?",
                            (str(uuid.uuid4()), row["id"]),
                        )
                    conn.commit()
                except sqlite3.OperationalError:
                    pass
                try:
                    conn.execute(
                        f"UPDATE {tbl} SET updated_at = COALESCE(updated_at, created_at, ?) WHERE updated_at IS NULL",
                        (_now(),),
                    )
                    conn.commit()
                except sqlite3.OperationalError:
                    pass

            # Backfill settings updated_at (settings has no created_at or id)
            try:
                conn.execute(
                    "UPDATE settings SET updated_at = ? WHERE updated_at IS NULL",
                    (_now(),),
                )
                conn.commit()
            except sqlite3.OperationalError:
                pass

            # Indexes that depend on migrated columns
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_liked ON history(liked)"
            )
            conn.commit()

            # Seed built-in templates if none exist
            builtin_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM templates WHERE is_builtin = 1"
            ).fetchone()["cnt"]
            if builtin_count == 0:
                conn.execute(
                    """INSERT INTO templates (name, test_type, tone, structure_instructions, closing_text, is_builtin)
                       VALUES (?, ?, ?, ?, ?, 1)""",
                    (
                        "Lipid Panel",
                        "Lipids",
                        "concerned",
                        "Patient should understand that their goal LDL is less than 70 and they are not yet at goal so we will be adjusting the therapeutic approach.",
                        "Please let us know if you have any questions.",
                    ),
                )
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
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, _now()),
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
        tone_preference: int | None = None,
        detail_preference: int | None = None,
    ) -> dict[str, Any]:
        conn = self._get_conn()
        try:
            sid = str(uuid.uuid4())
            now = _now()
            cursor = conn.execute(
                """INSERT INTO history (test_type, test_type_display, filename, summary, full_response, tone_preference, detail_preference, sync_id, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    test_type,
                    test_type_display,
                    filename,
                    summary,
                    json.dumps(full_response),
                    tone_preference,
                    detail_preference,
                    sid,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM history WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            result = dict(row)
            result["full_response"] = json.loads(result["full_response"])
            return result
        finally:
            conn.close()

    def list_history(
        self,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        liked_only: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        conn = self._get_conn()
        try:
            conditions: list[str] = []
            params: list[Any] = []

            if search:
                like = f"%{search}%"
                conditions.append(
                    "(summary LIKE ? OR test_type_display LIKE ? OR filename LIKE ?)"
                )
                params.extend([like, like, like])

            if liked_only:
                conditions.append("liked = 1")

            where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

            count_row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM history{where_clause}",
                params,
            ).fetchone()
            total = count_row["cnt"]

            rows = conn.execute(
                f"""SELECT id, created_at, test_type, test_type_display, filename, summary, liked, sync_id, updated_at
                    FROM history{where_clause}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?""",
                params + [limit, offset],
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

    def update_history_liked(self, history_id: int, liked: bool) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "UPDATE history SET liked = ?, updated_at = ? WHERE id = ?",
                (1 if liked else 0, _now(), history_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def mark_copied(self, history_id: int) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "UPDATE history SET copied = 1, updated_at = ? WHERE id = ?",
                (_now(), history_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_liked_examples(
        self,
        limit: int = 2,
        test_type: str | None = None,
        tone_preference: int | None = None,
        detail_preference: int | None = None,
    ) -> list[dict]:
        conn = self._get_conn()
        try:
            conditions = ["(liked = 1 OR copied = 1)"]
            params: list[Any] = []
            if test_type:
                conditions.append("test_type = ?")
                params.append(test_type)
            if tone_preference is not None:
                conditions.append("tone_preference = ?")
                params.append(tone_preference)
            if detail_preference is not None:
                conditions.append("detail_preference = ?")
                params.append(detail_preference)
            where_clause = " WHERE " + " AND ".join(conditions)
            params.append(limit)
            rows = conn.execute(
                f"""SELECT full_response FROM history{where_clause}
                    ORDER BY liked DESC, copied DESC, created_at DESC LIMIT ?""",
                params,
            ).fetchall()

            examples: list[dict] = []
            for row in rows:
                try:
                    full_response = json.loads(row["full_response"])
                    explanation = full_response.get("explanation", {})
                    overall_summary = explanation.get("overall_summary", "")
                    key_findings = explanation.get("key_findings", [])[:2]
                    if overall_summary:
                        examples.append({
                            "overall_summary": overall_summary,
                            "key_findings": key_findings,
                        })
                except (json.JSONDecodeError, TypeError):
                    continue
            return examples
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
            sid = str(uuid.uuid4())
            cursor = conn.execute(
                """INSERT INTO templates (name, test_type, tone, structure_instructions, closing_text, sync_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name, test_type, tone, structure_instructions, closing_text, sid),
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

    # --- Letters ---

    def save_letter(
        self,
        prompt: str,
        content: str,
        letter_type: str = "general",
        model_used: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> int:
        conn = self._get_conn()
        try:
            sid = str(uuid.uuid4())
            now = _now()
            cursor = conn.execute(
                """INSERT INTO letters (prompt, content, letter_type, model_used, input_tokens, output_tokens, sync_id, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (prompt, content, letter_type, model_used, input_tokens, output_tokens, sid, now),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]
        finally:
            conn.close()

    def list_letters(
        self,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
        liked_only: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        conn = self._get_conn()
        try:
            conditions: list[str] = []
            params: list[Any] = []

            if search:
                like = f"%{search}%"
                conditions.append("(content LIKE ? OR prompt LIKE ?)")
                params.extend([like, like])

            if liked_only:
                conditions.append("liked = 1")

            where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

            count_row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM letters{where_clause}",
                params,
            ).fetchone()
            total = count_row["cnt"]
            rows = conn.execute(
                f"""SELECT * FROM letters{where_clause}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?""",
                params + [limit, offset],
            ).fetchall()
            return [dict(row) for row in rows], total
        finally:
            conn.close()

    def update_letter(self, letter_id: int, content: str) -> dict[str, Any] | None:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "UPDATE letters SET content = ?, updated_at = ? WHERE id = ?",
                (content, _now(), letter_id),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return None
            return self.get_letter(letter_id)
        finally:
            conn.close()

    def toggle_letter_liked(self, letter_id: int, liked: bool) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "UPDATE letters SET liked = ?, updated_at = ? WHERE id = ?",
                (1 if liked else 0, _now(), letter_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_letter(self, letter_id: int) -> dict[str, Any] | None:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM letters WHERE id = ?", (letter_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def delete_letter(self, letter_id: int) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM letters WHERE id = ?", (letter_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # --- Teaching Points ---

    def create_teaching_point(
        self, text: str, test_type: str | None = None,
    ) -> dict[str, Any]:
        conn = self._get_conn()
        try:
            sid = str(uuid.uuid4())
            now = _now()
            cursor = conn.execute(
                "INSERT INTO teaching_points (text, test_type, sync_id, updated_at) VALUES (?, ?, ?, ?)",
                (text, test_type, sid, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM teaching_points WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def list_teaching_points(
        self, test_type: str | None = None,
    ) -> list[dict[str, Any]]:
        conn = self._get_conn()
        try:
            if test_type:
                rows = conn.execute(
                    "SELECT * FROM teaching_points WHERE test_type IS NULL OR test_type = ? ORDER BY created_at DESC",
                    (test_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM teaching_points ORDER BY created_at DESC",
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def update_teaching_point(
        self, point_id: int, text: str | None = None, test_type: str | None = "UNSET",
    ) -> dict[str, Any] | None:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM teaching_points WHERE id = ?", (point_id,),
            ).fetchone()
            if row is None:
                return None
            current = dict(row)
            new_text = text if text is not None else current["text"]
            new_test_type = current["test_type"] if test_type == "UNSET" else test_type
            conn.execute(
                "UPDATE teaching_points SET text = ?, test_type = ?, updated_at = ? WHERE id = ?",
                (new_text, new_test_type, _now(), point_id),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT * FROM teaching_points WHERE id = ?", (point_id,),
            ).fetchone()
            return dict(updated)
        finally:
            conn.close()

    def delete_teaching_point(self, point_id: int) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM teaching_points WHERE id = ?", (point_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


    # --- Sync Helpers ---

    def export_table(self, table: str) -> list[dict[str, Any]]:
        """Return all rows from a table as dicts."""
        allowed = {"settings", "history", "templates", "letters", "teaching_points"}
        if table not in allowed:
            return []
        conn = self._get_conn()
        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            results = [dict(row) for row in rows]
            if table == "history":
                for r in results:
                    if isinstance(r.get("full_response"), str):
                        r["full_response"] = json.loads(r["full_response"])
            return results
        finally:
            conn.close()

    def export_record(self, table: str, record_id: int) -> dict[str, Any] | None:
        """Return a single row by local id."""
        allowed = {"settings", "history", "templates", "letters", "teaching_points"}
        if table not in allowed:
            return None
        conn = self._get_conn()
        try:
            if table == "settings":
                return None  # settings don't have integer ids
            row = conn.execute(
                f"SELECT * FROM {table} WHERE id = ?", (record_id,)
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            if table == "history" and isinstance(result.get("full_response"), str):
                result["full_response"] = json.loads(result["full_response"])
            return result
        finally:
            conn.close()

    def merge_settings_row(self, key: str, value: str, updated_at: str) -> bool:
        """Merge a remote settings row. Returns True if local was updated."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT updated_at FROM settings WHERE key = ?", (key,)
            ).fetchone()
            if row and row["updated_at"] and row["updated_at"] >= updated_at:
                return False
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, updated_at),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def merge_record(self, table: str, remote_row: dict[str, Any]) -> bool:
        """Merge a remote row by sync_id. Returns True if local was updated."""
        allowed = {"history", "templates", "letters", "teaching_points"}
        if table not in allowed:
            return False
        conn = self._get_conn()
        try:
            sync_id = remote_row.get("sync_id")
            if not sync_id:
                return False

            local = conn.execute(
                f"SELECT id, updated_at FROM {table} WHERE sync_id = ?",
                (sync_id,),
            ).fetchone()

            remote_updated = remote_row.get("updated_at", "")

            if local:
                local_updated = local["updated_at"] or ""
                if local_updated >= remote_updated:
                    return False
                # Update local row
                cols_to_update = {
                    k: v for k, v in remote_row.items()
                    if k not in ("id", "sync_id")
                }
                if not cols_to_update:
                    return False
                # Serialize full_response for history
                if table == "history" and "full_response" in cols_to_update:
                    fr = cols_to_update["full_response"]
                    if isinstance(fr, dict):
                        cols_to_update["full_response"] = json.dumps(fr)
                # Coerce booleans to int for SQLite
                for k, v in cols_to_update.items():
                    if isinstance(v, bool):
                        cols_to_update[k] = 1 if v else 0
                set_clause = ", ".join(f"{k} = ?" for k in cols_to_update)
                values = list(cols_to_update.values()) + [local["id"]]
                conn.execute(
                    f"UPDATE {table} SET {set_clause} WHERE id = ?",
                    values,
                )
                conn.commit()
                return True
            else:
                # Insert new row
                insert_data = {
                    k: v for k, v in remote_row.items() if k != "id"
                }
                if table == "history" and "full_response" in insert_data:
                    fr = insert_data["full_response"]
                    if isinstance(fr, dict):
                        insert_data["full_response"] = json.dumps(fr)
                # Coerce booleans to int for SQLite
                for k, v in insert_data.items():
                    if isinstance(v, bool):
                        insert_data[k] = 1 if v else 0
                cols = ", ".join(insert_data.keys())
                placeholders = ", ".join("?" for _ in insert_data)
                conn.execute(
                    f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                    list(insert_data.values()),
                )
                conn.commit()
                return True
        finally:
            conn.close()


_db_instance: Database | None = None


def get_db() -> Database:
    """Return the module-level Database singleton."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance
