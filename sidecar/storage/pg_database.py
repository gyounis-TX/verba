"""PostgreSQL database for web mode (multi-tenant, Supabase-backed).

Drop-in replacement for the SQLite Database class. Every query is scoped by user_id.
Uses asyncpg connection pool via DATABASE_URL env var.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")


def _now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Reuse stylistic pattern extraction from the SQLite module
from storage.database import _extract_stylistic_patterns


_pool = None


def _parse_database_url(url: str) -> dict:
    """Parse DATABASE_URL into asyncpg-compatible connection parameters.

    Python 3.12's urllib has strict URL parsing that chokes on passwords
    with special characters. Parse manually to avoid this.
    """
    # postgresql://user:password@host:port/dbname
    import re as _re

    m = _re.match(
        r"^postgres(?:ql)?://([^:]+):(.+)@([^:/@]+):(\d+)/(.+)$", url
    )
    if not m:
        raise ValueError(f"Cannot parse DATABASE_URL: {url[:30]}...")
    return {
        "user": m.group(1),
        "password": m.group(2),
        "host": m.group(3),
        "port": int(m.group(4)),
        "database": m.group(5),
    }


async def _get_pool():
    """Return the asyncpg connection pool, creating it on first call."""
    global _pool
    if _pool is None:
        import asyncpg
        import ssl as _ssl

        params = _parse_database_url(DATABASE_URL)
        # Supabase requires SSL for direct connections
        ssl_ctx = _ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = _ssl.CERT_NONE

        # Resolve hostname to IPv4 explicitly to avoid IPv6 unreachable errors
        import socket as _socket
        host = params.pop("host")
        ipv4 = _socket.getaddrinfo(host, None, _socket.AF_INET)[0][4][0]
        logger.info("Resolved %s -> %s", host, ipv4)

        _pool = await asyncpg.create_pool(
            min_size=2,
            max_size=10,
            ssl=ssl_ctx,
            host=ipv4,
            server_settings={"search_path": "public"},
            **params,
        )
        logger.info("PostgreSQL connection pool initialized")
    return _pool


async def close_pool():
    """Close the connection pool (for graceful shutdown)."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL connection pool closed")


class PgDatabase:
    """PostgreSQL-backed storage for web mode (multi-tenant)."""

    # --- Settings ---

    async def get_setting(self, key: str, user_id: str | None = None) -> str | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            if user_id:
                row = await conn.fetchrow(
                    "SELECT value FROM settings WHERE key = $1 AND user_id = $2",
                    key, user_id,
                )
            else:
                row = await conn.fetchrow(
                    "SELECT value FROM settings WHERE key = $1", key,
                )
            return row["value"] if row else None

    async def set_setting(self, key: str, value: str, user_id: str | None = None) -> None:
        pool = await _get_pool()
        now = _now()
        async with pool.acquire() as conn:
            if user_id:
                await conn.execute(
                    """INSERT INTO settings (user_id, key, value, updated_at)
                       VALUES ($1, $2, $3, $4)
                       ON CONFLICT (user_id, key) DO UPDATE SET value = $3, updated_at = $4""",
                    user_id, key, value, now,
                )
            else:
                await conn.execute(
                    """INSERT INTO settings (key, value, updated_at)
                       VALUES ($1, $2, $3)
                       ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = $3""",
                    key, value, now,
                )

    async def get_all_settings(self, user_id: str | None = None) -> dict[str, str]:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            if user_id:
                rows = await conn.fetch(
                    "SELECT key, value FROM settings WHERE user_id = $1", user_id,
                )
            else:
                rows = await conn.fetch("SELECT key, value FROM settings")
            return {row["key"]: row["value"] for row in rows}

    async def delete_setting(self, key: str, user_id: str | None = None) -> None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            if user_id:
                await conn.execute(
                    "DELETE FROM settings WHERE key = $1 AND user_id = $2",
                    key, user_id,
                )
            else:
                await conn.execute("DELETE FROM settings WHERE key = $1", key)

    # --- History ---

    async def save_history(
        self,
        test_type: str,
        test_type_display: str,
        summary: str,
        full_response: dict[str, Any],
        filename: str | None = None,
        tone_preference: int | None = None,
        detail_preference: int | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        pool = await _get_pool()
        record_id = str(uuid.uuid4())
        sync_id = str(uuid.uuid4())
        now = _now()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO history
                   (id, user_id, sync_id, test_type, test_type_display, filename,
                    summary, full_response, tone_preference, detail_preference,
                    created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)""",
                record_id, user_id, sync_id, test_type, test_type_display,
                filename, summary, json.dumps(full_response),
                tone_preference, detail_preference, now, now,
            )
            row = await conn.fetchrow(
                "SELECT * FROM history WHERE id = $1 AND user_id = $2",
                record_id, user_id,
            )
        result = dict(row)
        if isinstance(result.get("full_response"), str):
            result["full_response"] = json.loads(result["full_response"])
        return result

    async def list_history(
        self,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        liked_only: bool = False,
        user_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        pool = await _get_pool()
        conditions = ["user_id = $1"]
        params: list[Any] = [user_id]
        idx = 2

        if search:
            like = f"%{search}%"
            conditions.append(
                f"(summary ILIKE ${idx} OR test_type_display ILIKE ${idx+1} OR filename ILIKE ${idx+2})"
            )
            params.extend([like, like, like])
            idx += 3

        if liked_only:
            conditions.append("liked = true")

        where = " WHERE " + " AND ".join(conditions)

        async with pool.acquire() as conn:
            count_row = await conn.fetchrow(
                f"SELECT COUNT(*) as cnt FROM history{where}", *params,
            )
            total = count_row["cnt"]

            rows = await conn.fetch(
                f"""SELECT id, created_at, test_type, test_type_display, filename,
                           summary, liked, sync_id, updated_at
                    FROM history{where}
                    ORDER BY created_at DESC
                    LIMIT ${idx} OFFSET ${idx+1}""",
                *params, limit, offset,
            )

        return [dict(row) for row in rows], total

    async def get_history(self, history_id: int | str, user_id: str | None = None) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM history WHERE id = $1 AND user_id = $2",
                str(history_id), user_id,
            )
        if not row:
            return None
        result = dict(row)
        if isinstance(result.get("full_response"), str):
            result["full_response"] = json.loads(result["full_response"])
        return result

    async def delete_history(self, history_id: int | str, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM history WHERE id = $1 AND user_id = $2",
                str(history_id), user_id,
            )
        return result.endswith("1")

    async def update_history_liked(self, history_id: int | str, liked: bool, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE history SET liked = $1, updated_at = $2 WHERE id = $3 AND user_id = $4",
                liked, _now(), str(history_id), user_id,
            )
        return result.endswith("1")

    async def mark_copied(self, history_id: int | str, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE history SET copied = true, updated_at = $1 WHERE id = $2 AND user_id = $3",
                _now(), str(history_id), user_id,
            )
        return result.endswith("1")

    async def save_edited_text(self, history_id: int | str, edited_text: str, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE history SET edited_text = $1, updated_at = $2 WHERE id = $3 AND user_id = $4",
                edited_text, _now(), str(history_id), user_id,
            )
        return result.endswith("1")

    async def get_recent_edits(
        self, test_type: str, limit: int = 3, user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT full_response, edited_text FROM history
                   WHERE user_id = $1 AND test_type = $2 AND edited_text IS NOT NULL
                   ORDER BY updated_at DESC LIMIT $3""",
                user_id, test_type, limit,
            )

        edits: list[dict[str, Any]] = []
        for row in rows:
            try:
                if not row["edited_text"]:
                    continue
                fr_raw = row["full_response"]
                full_response = json.loads(fr_raw) if isinstance(fr_raw, str) else fr_raw
                original = full_response.get("explanation", {}).get("overall_summary", "")
                edited = row["edited_text"]
                if not original:
                    continue

                original_len = len(original)
                edited_len = len(edited)
                length_change_pct = ((edited_len - original_len) / original_len * 100) if original_len > 0 else 0
                original_paragraphs = len([p for p in original.split("\n\n") if p.strip()])
                edited_paragraphs = len([p for p in edited.split("\n\n") if p.strip()])

                edits.append({
                    "length_change_pct": round(length_change_pct, 1),
                    "paragraph_change": edited_paragraphs - original_paragraphs,
                    "shorter": edited_len < original_len,
                    "longer": edited_len > original_len,
                })
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
        return edits

    async def get_learned_phrases(
        self, test_type: str | None = None, limit: int = 10, user_id: str | None = None,
    ) -> list[str]:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            if test_type:
                rows = await conn.fetch(
                    """SELECT full_response, edited_text FROM history
                       WHERE user_id = $1 AND test_type = $2 AND edited_text IS NOT NULL
                       ORDER BY updated_at DESC LIMIT 20""",
                    user_id, test_type,
                )
            else:
                rows = await conn.fetch(
                    """SELECT full_response, edited_text FROM history
                       WHERE user_id = $1 AND edited_text IS NOT NULL
                       ORDER BY updated_at DESC LIMIT 20""",
                    user_id,
                )

        added_phrases: dict[str, int] = {}
        for row in rows:
            try:
                if not row["edited_text"]:
                    continue
                fr_raw = row["full_response"]
                full_response = json.loads(fr_raw) if isinstance(fr_raw, str) else fr_raw
                original = full_response.get("explanation", {}).get("overall_summary", "")
                edited = row["edited_text"]
                if not original or not edited:
                    continue

                original_lower = original.lower()
                sentences = re.split(r'(?<=[.!?])\s+', edited)
                for sentence in sentences:
                    sentence = sentence.strip()
                    if len(sentence) < 10 or len(sentence) > 150:
                        continue
                    sentence_lower = sentence.lower()
                    if sentence_lower not in original_lower:
                        normalized = sentence_lower[:80]
                        added_phrases[normalized] = added_phrases.get(normalized, 0) + 1
            except (json.JSONDecodeError, TypeError, KeyError):
                continue

        frequent_phrases = [
            phrase for phrase, count in sorted(
                added_phrases.items(), key=lambda x: -x[1]
            )
            if count >= 2
        ][:limit]
        return frequent_phrases

    async def get_prior_measurements(
        self, test_type: str, limit: int = 3, user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT created_at, full_response FROM history
                   WHERE user_id = $1 AND test_type = $2
                   ORDER BY created_at DESC LIMIT $3""",
                user_id, test_type, limit,
            )

        results: list[dict[str, Any]] = []
        for row in rows:
            try:
                fr_raw = row["full_response"]
                full_response = json.loads(fr_raw) if isinstance(fr_raw, str) else fr_raw
                parsed_report = full_response.get("parsed_report", {})
                measurements = parsed_report.get("measurements", [])

                created_at = str(row["created_at"]) if row["created_at"] else "Unknown"
                date_str = created_at[:10]

                measurement_summary = [
                    {
                        "abbreviation": m.get("abbreviation", ""),
                        "value": m.get("value"),
                        "unit": m.get("unit", ""),
                        "status": m.get("status", ""),
                    }
                    for m in measurements
                    if m.get("abbreviation") and m.get("value") is not None
                ]

                if measurement_summary:
                    results.append({
                        "date": date_str,
                        "measurements": measurement_summary,
                    })
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
        return results

    async def get_liked_examples(
        self,
        limit: int = 2,
        test_type: str | None = None,
        tone_preference: int | None = None,
        detail_preference: int | None = None,
        user_id: str | None = None,
    ) -> list[dict]:
        pool = await _get_pool()
        conditions = ["user_id = $1", "(liked = true OR copied = true)"]
        params: list[Any] = [user_id]
        idx = 2

        if test_type:
            conditions.append(f"test_type = ${idx}")
            params.append(test_type)
            idx += 1
        if tone_preference is not None:
            conditions.append(f"tone_preference = ${idx}")
            params.append(tone_preference)
            idx += 1
        if detail_preference is not None:
            conditions.append(f"detail_preference = ${idx}")
            params.append(detail_preference)
            idx += 1

        where = " WHERE " + " AND ".join(conditions)
        params.append(limit)

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT full_response FROM history{where}
                    ORDER BY liked DESC, copied DESC, created_at DESC LIMIT ${idx}""",
                *params,
            )

        examples: list[dict] = []
        for row in rows:
            try:
                fr_raw = row["full_response"]
                full_response = json.loads(fr_raw) if isinstance(fr_raw, str) else fr_raw
                explanation = full_response.get("explanation", {})
                overall_summary = explanation.get("overall_summary", "")
                key_findings = explanation.get("key_findings", [])
                if not overall_summary:
                    continue

                paragraphs = [p for p in overall_summary.split("\n\n") if p.strip()]
                sentences = overall_summary.replace("\n", " ").split(". ")
                stylistic_patterns = _extract_stylistic_patterns(overall_summary)

                examples.append({
                    "paragraph_count": len(paragraphs),
                    "approx_sentence_count": len(sentences),
                    "approx_char_length": len(overall_summary),
                    "num_key_findings": len(key_findings),
                    "finding_severities": [
                        kf.get("severity", "")
                        for kf in key_findings
                        if kf.get("severity")
                    ][:5],
                    "stylistic_patterns": stylistic_patterns,
                })
            except (json.JSONDecodeError, TypeError):
                continue
        return examples

    # --- Templates ---

    async def create_template(
        self,
        name: str,
        test_type: str | None = None,
        tone: str | None = None,
        structure_instructions: str | None = None,
        closing_text: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        pool = await _get_pool()
        record_id = str(uuid.uuid4())
        sync_id = str(uuid.uuid4())
        now = _now()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO templates
                   (id, user_id, sync_id, name, test_type, tone,
                    structure_instructions, closing_text, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                record_id, user_id, sync_id, name, test_type, tone,
                structure_instructions, closing_text, now, now,
            )
            row = await conn.fetchrow(
                "SELECT * FROM templates WHERE id = $1 AND user_id = $2",
                record_id, user_id,
            )
        return dict(row)

    async def list_templates(self, user_id: str | None = None) -> tuple[list[dict[str, Any]], int]:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            count_row = await conn.fetchrow(
                "SELECT COUNT(*) as cnt FROM templates WHERE user_id = $1", user_id,
            )
            total = count_row["cnt"]
            rows = await conn.fetch(
                "SELECT * FROM templates WHERE user_id = $1 ORDER BY created_at DESC",
                user_id,
            )
        return [dict(row) for row in rows], total

    async def get_template(self, template_id: int | str, user_id: str | None = None) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM templates WHERE id = $1 AND user_id = $2",
                str(template_id), user_id,
            )
        return dict(row) if row else None

    async def update_template(self, template_id: int | str, user_id: str | None = None, **kwargs: Any) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT * FROM templates WHERE id = $1 AND user_id = $2",
                str(template_id), user_id,
            )
            if not existing:
                return None

            allowed = {"name", "test_type", "tone", "structure_instructions", "closing_text", "is_default"}
            updates = {k: v for k, v in kwargs.items() if k in allowed}
            if not updates:
                return dict(existing)

            # If setting as default, clear other defaults for the same test_type
            if updates.get("is_default"):
                test_type = updates.get("test_type", existing["test_type"])
                if test_type:
                    await conn.execute(
                        "UPDATE templates SET is_default = false WHERE test_type = $1 AND id != $2 AND user_id = $3",
                        test_type, str(template_id), user_id,
                    )

            set_parts = []
            values: list[Any] = []
            idx = 1
            for k, v in updates.items():
                set_parts.append(f"{k} = ${idx}")
                values.append(v)
                idx += 1
            set_parts.append(f"updated_at = ${idx}")
            values.append(_now())
            idx += 1
            values.append(str(template_id))
            values.append(user_id)

            await conn.execute(
                f"UPDATE templates SET {', '.join(set_parts)} WHERE id = ${idx} AND user_id = ${idx+1}",
                *values,
            )

        return await self.get_template(template_id, user_id=user_id)

    async def get_default_template_for_type(self, test_type: str, user_id: str | None = None) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM templates WHERE test_type = $1 AND is_default = true AND user_id = $2 LIMIT 1",
                test_type, user_id,
            )
        return dict(row) if row else None

    async def delete_template(self, template_id: int | str, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM templates WHERE id = $1 AND user_id = $2",
                str(template_id), user_id,
            )
        return result.endswith("1")

    # --- Letters ---

    async def save_letter(
        self,
        prompt: str,
        content: str,
        letter_type: str = "general",
        model_used: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        user_id: str | None = None,
    ) -> str:
        pool = await _get_pool()
        record_id = str(uuid.uuid4())
        sync_id = str(uuid.uuid4())
        now = _now()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO letters
                   (id, user_id, sync_id, prompt, content, letter_type,
                    model_used, input_tokens, output_tokens, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
                record_id, user_id, sync_id, prompt, content, letter_type,
                model_used, input_tokens, output_tokens, now, now,
            )
        return record_id

    async def list_letters(
        self,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
        liked_only: bool = False,
        user_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        pool = await _get_pool()
        conditions = ["user_id = $1"]
        params: list[Any] = [user_id]
        idx = 2

        if search:
            like = f"%{search}%"
            conditions.append(f"(content ILIKE ${idx} OR prompt ILIKE ${idx+1})")
            params.extend([like, like])
            idx += 2

        if liked_only:
            conditions.append("liked = true")

        where = " WHERE " + " AND ".join(conditions)

        async with pool.acquire() as conn:
            count_row = await conn.fetchrow(
                f"SELECT COUNT(*) as cnt FROM letters{where}", *params,
            )
            total = count_row["cnt"]
            rows = await conn.fetch(
                f"""SELECT * FROM letters{where}
                    ORDER BY created_at DESC
                    LIMIT ${idx} OFFSET ${idx+1}""",
                *params, limit, offset,
            )
        return [dict(row) for row in rows], total

    async def update_letter(self, letter_id: int | str, content: str, user_id: str | None = None) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE letters SET content = $1, updated_at = $2 WHERE id = $3 AND user_id = $4",
                content, _now(), str(letter_id), user_id,
            )
            if not result.endswith("1"):
                return None
            row = await conn.fetchrow(
                "SELECT * FROM letters WHERE id = $1 AND user_id = $2",
                str(letter_id), user_id,
            )
        return dict(row) if row else None

    async def toggle_letter_liked(self, letter_id: int | str, liked: bool, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE letters SET liked = $1, updated_at = $2 WHERE id = $3 AND user_id = $4",
                liked, _now(), str(letter_id), user_id,
            )
        return result.endswith("1")

    async def get_letter(self, letter_id: int | str, user_id: str | None = None) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM letters WHERE id = $1 AND user_id = $2",
                str(letter_id), user_id,
            )
        return dict(row) if row else None

    async def delete_letter(self, letter_id: int | str, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM letters WHERE id = $1 AND user_id = $2",
                str(letter_id), user_id,
            )
        return result.endswith("1")

    # --- Teaching Points ---

    async def create_teaching_point(
        self, text: str, test_type: str | None = None, user_id: str | None = None,
    ) -> dict[str, Any]:
        pool = await _get_pool()
        record_id = str(uuid.uuid4())
        sync_id = str(uuid.uuid4())
        now = _now()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO teaching_points
                   (id, user_id, sync_id, test_type, text, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                record_id, user_id, sync_id, test_type, text, now, now,
            )
            row = await conn.fetchrow(
                "SELECT * FROM teaching_points WHERE id = $1 AND user_id = $2",
                record_id, user_id,
            )
        return dict(row)

    async def list_teaching_points(
        self, test_type: str | None = None, user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            if test_type:
                rows = await conn.fetch(
                    """SELECT * FROM teaching_points
                       WHERE user_id = $1 AND (test_type IS NULL OR test_type = $2)
                       ORDER BY created_at DESC""",
                    user_id, test_type,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM teaching_points WHERE user_id = $1 ORDER BY created_at DESC",
                    user_id,
                )
        return [dict(row) for row in rows]

    async def update_teaching_point(
        self, point_id: int | str, text: str | None = None,
        test_type: str | None = "UNSET", user_id: str | None = None,
    ) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM teaching_points WHERE id = $1 AND user_id = $2",
                str(point_id), user_id,
            )
            if row is None:
                return None
            current = dict(row)
            new_text = text if text is not None else current["text"]
            new_test_type = current["test_type"] if test_type == "UNSET" else test_type
            await conn.execute(
                "UPDATE teaching_points SET text = $1, test_type = $2, updated_at = $3 WHERE id = $4 AND user_id = $5",
                new_text, new_test_type, _now(), str(point_id), user_id,
            )
            updated = await conn.fetchrow(
                "SELECT * FROM teaching_points WHERE id = $1 AND user_id = $2",
                str(point_id), user_id,
            )
        return dict(updated) if updated else None

    async def delete_teaching_point(self, point_id: int | str, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM teaching_points WHERE id = $1 AND user_id = $2",
                str(point_id), user_id,
            )
        return result.endswith("1")

    async def list_history_test_types(self, user_id: str | None = None) -> list[dict[str, str]]:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT DISTINCT test_type, test_type_display FROM history
                   WHERE user_id = $1
                   ORDER BY test_type_display""",
                user_id,
            )
        return [dict(row) for row in rows]

    # --- Shared Teaching Points (stubs for web mode) ---
    # In web mode, sharing is handled at the Supabase level, not locally cached.

    async def replace_shared_teaching_points(self, rows: list[dict], user_id: str | None = None) -> int:
        return 0

    async def list_shared_teaching_points(
        self, test_type: str | None = None, user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return []

    async def list_all_teaching_points_for_prompt(
        self, test_type: str | None = None, user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        own = await self.list_teaching_points(test_type=test_type, user_id=user_id)
        for tp in own:
            tp["source"] = "own"
        return own

    async def purge_shared_duplicates_from_own(self, user_id: str | None = None) -> int:
        return 0

    # --- Shared Templates (stubs for web mode) ---

    async def replace_shared_templates(self, rows: list[dict], user_id: str | None = None) -> int:
        return 0

    async def get_shared_template_by_sync_id(self, sync_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        return None

    async def list_shared_templates(self, user_id: str | None = None) -> list[dict[str, Any]]:
        return []

    # --- Sync Helpers (stubs for web mode) ---
    # In web mode, sync is handled at the Supabase/cloud level.

    async def export_table(self, table: str, user_id: str | None = None) -> list[dict[str, Any]]:
        return []

    async def export_record(self, table: str, record_id: int | str, user_id: str | None = None) -> dict[str, Any] | None:
        return None

    async def merge_settings_row(self, key: str, value: str, updated_at: str, user_id: str | None = None) -> bool:
        return False

    async def merge_record(self, table: str, remote_row: dict[str, Any], user_id: str | None = None) -> bool:
        return False


_pg_instance: PgDatabase | None = None


def get_pg_db() -> PgDatabase:
    """Return the module-level PgDatabase singleton."""
    global _pg_instance
    if _pg_instance is None:
        _pg_instance = PgDatabase()
    return _pg_instance
