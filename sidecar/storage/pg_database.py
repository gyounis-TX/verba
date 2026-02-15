"""PostgreSQL database for web mode (multi-tenant, RDS-backed).

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


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert native PostgreSQL types (datetime, UUID) to JSON-compatible primitives.

    Also ensures an 'id' field exists — rows synced from desktop may
    only have 'sync_id', while Pydantic models require 'id'.
    """
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.strftime("%Y-%m-%dT%H:%M:%SZ")
        elif isinstance(v, uuid.UUID):
            out[k] = str(v)
        else:
            out[k] = v
    # Ensure 'id' exists — fall back to sync_id for rows synced from desktop
    if out.get("id") is None and out.get("sync_id"):
        out["id"] = out["sync_id"]
    return out

DATABASE_URL = os.getenv("DATABASE_URL", "")


def _now() -> datetime:
    """Return current UTC time as a datetime object (asyncpg requires native types)."""
    return datetime.now(timezone.utc)


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

        params = _parse_database_url(DATABASE_URL)

        # RDS requires SSL. Use a permissive context (no cert verification)
        # since we're connecting within the same VPC.
        import ssl as _ssl
        ssl_ctx = _ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = _ssl.CERT_NONE
        ssl_arg = ssl_ctx

        _pool = await asyncpg.create_pool(
            min_size=2,
            max_size=10,
            ssl=ssl_arg,
            server_settings={"search_path": "public"},
            **params,
        )
        logger.info("PostgreSQL connection pool initialized")
    return _pool


async def run_migrations():
    """Run the idempotent schema migration on startup.

    All statements use IF NOT EXISTS / ON CONFLICT DO NOTHING,
    so this is safe to execute on every boot.
    """
    pool = await _get_pool()
    sql_path = os.path.join(os.path.dirname(__file__), "migrations", "schema.sql")
    if not os.path.exists(sql_path):
        logger.warning("Migration file not found at %s — skipping", sql_path)
        return
    with open(sql_path) as f:
        sql = f.read()
    async with pool.acquire() as conn:
        await conn.execute(sql)
    logger.info("Database migrations applied successfully")


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
        severity_score: float | None = None,
    ) -> dict[str, Any]:
        pool = await _get_pool()
        sync_id = str(uuid.uuid4())
        now = _now()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO history
                   (user_id, sync_id, test_type, test_type_display, filename,
                    summary, full_response, tone_preference, detail_preference,
                    created_at, updated_at, severity_score)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)""",
                user_id, sync_id, test_type, test_type_display,
                filename, summary, json.dumps(full_response),
                tone_preference, detail_preference, now, now,
                severity_score,
            )
            row = await conn.fetchrow(
                "SELECT * FROM history WHERE sync_id = $1 AND user_id = $2",
                sync_id, user_id,
            )
        result = _normalize_row(dict(row))
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
                f"""SELECT sync_id AS id, created_at, test_type, test_type_display, filename,
                           summary, liked, sync_id, updated_at
                    FROM history{where}
                    ORDER BY created_at DESC
                    LIMIT ${idx} OFFSET ${idx+1}""",
                *params, limit, offset,
            )

        return [_normalize_row(dict(row)) for row in rows], total

    async def get_history(self, history_id: int | str, user_id: str | None = None) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM history WHERE sync_id = $1 AND user_id = $2",
                str(history_id), user_id,
            )
        if not row:
            return None
        result = _normalize_row(dict(row))
        if isinstance(result.get("full_response"), str):
            result["full_response"] = json.loads(result["full_response"])
        return result

    async def delete_history(self, history_id: int | str, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM history WHERE sync_id = $1 AND user_id = $2",
                str(history_id), user_id,
            )
        return result.endswith("1")

    async def update_history_liked(self, history_id: int | str, liked: bool, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE history SET liked = $1, updated_at = $2 WHERE sync_id = $3 AND user_id = $4",
                liked, _now(), str(history_id), user_id,
            )
        return result.endswith("1")

    async def mark_copied(self, history_id: int | str, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE history SET copied = true, updated_at = $1 WHERE sync_id = $2 AND user_id = $3",
                _now(), str(history_id), user_id,
            )
        return result.endswith("1")

    async def rate_history(self, history_id: int | str, rating: int, note: str | None = None, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE history SET quality_rating = $1, quality_note = $2, updated_at = $3 WHERE sync_id = $4 AND user_id = $5",
                rating, note, _now(), str(history_id), user_id,
            )
        return result.endswith("1")

    async def get_recent_feedback(
        self, test_type: str, limit: int = 5, user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT quality_rating, quality_note FROM history
                   WHERE user_id = $1 AND test_type = $2
                     AND quality_rating IS NOT NULL AND quality_rating <= 3
                     AND quality_note IS NOT NULL AND quality_note != ''
                   ORDER BY updated_at DESC LIMIT $3""",
                user_id, test_type, limit,
            )
        return [dict(row) for row in rows]

    async def save_history_settings_used(
        self, history_id: int | str, tone: int | None, detail: int | None,
        literacy: str | None, was_edited: bool = False, user_id: str | None = None,
    ) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            if tone is None and detail is None and literacy is None:
                result = await conn.execute(
                    "UPDATE history SET was_edited = $1, updated_at = $2 WHERE sync_id = $3 AND user_id = $4",
                    was_edited, _now(), str(history_id), user_id,
                )
            else:
                result = await conn.execute(
                    """UPDATE history SET tone_used = $1, detail_used = $2,
                       literacy_used = $3, was_edited = $4, updated_at = $5
                       WHERE sync_id = $6 AND user_id = $7""",
                    tone, detail, literacy, was_edited, _now(), str(history_id), user_id,
                )
        return result.endswith("1")

    async def get_optimal_settings(self, test_type: str, min_samples: int = 5, user_id: str | None = None) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT tone_used, detail_used, COUNT(*) as cnt,
                          SUM(CASE WHEN was_edited THEN 1 ELSE 0 END) as edit_count
                   FROM history
                   WHERE user_id = $1 AND test_type = $2 AND tone_used IS NOT NULL AND detail_used IS NOT NULL
                   GROUP BY tone_used, detail_used
                   HAVING COUNT(*) >= $3
                   ORDER BY (CAST(SUM(CASE WHEN was_edited THEN 1 ELSE 0 END) AS REAL) / COUNT(*))
                   LIMIT 1""",
                user_id, test_type, min_samples,
            )
        if not rows:
            return None
        r = dict(rows[0])
        return {
            "tone": r["tone_used"],
            "detail": r["detail_used"],
            "sample_count": r["cnt"],
            "edit_rate": round(r["edit_count"] / r["cnt"], 2),
        }

    async def get_style_profile(self, test_type: str, user_id: str | None = None, severity_band: str | None = None) -> dict[str, Any] | None:
        pool = await _get_pool()
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT profile, sample_count FROM style_profiles WHERE test_type = $1 AND user_id = $2",
                    test_type, user_id,
                )
            if not row:
                return None
            profile_raw = row["profile"]
            profile = json.loads(profile_raw) if isinstance(profile_raw, str) else profile_raw
            # Apply severity-band overrides if present
            if severity_band and "severity_overrides" in profile:
                overrides = profile["severity_overrides"].get(severity_band, {})
                if overrides:
                    merged = dict(profile)
                    merged.pop("severity_overrides", None)
                    merged.update(overrides)
                    return {"profile": merged, "sample_count": row["sample_count"]}
            return {"profile": profile, "sample_count": row["sample_count"]}
        except Exception:
            return None

    async def update_style_profile(
        self, test_type: str, new_data: dict[str, Any], alpha: float = 0.3,
        user_id: str | None = None, severity_band: str | None = None,
        created_at: str | None = None,
    ) -> None:
        from storage.database import _merge_profile, _compute_adaptive_alpha
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT profile, sample_count, updated_at AS last_updated FROM style_profiles WHERE test_type = $1 AND user_id = $2",
                test_type, user_id,
            )

            effective_alpha = alpha
            if created_at and row and row["last_updated"]:
                last_upd = str(row["last_updated"]) if row["last_updated"] else None
                if last_upd:
                    effective_alpha = _compute_adaptive_alpha(alpha, created_at, last_upd)

            if row:
                profile_raw = row["profile"]
                existing = json.loads(profile_raw) if isinstance(profile_raw, str) else profile_raw
                sample_count = row["sample_count"] + 1
            else:
                existing = {}
                sample_count = 1

            if severity_band:
                overrides = existing.get("severity_overrides", {})
                band_data = overrides.get(severity_band, {})
                if band_data:
                    merged_band = _merge_profile(band_data, new_data, effective_alpha)
                else:
                    merged_band = new_data
                overrides[severity_band] = merged_band
                existing["severity_overrides"] = overrides
                merged = existing
            else:
                if row:
                    sev_overrides = existing.pop("severity_overrides", None)
                    merged = _merge_profile(existing, new_data, effective_alpha)
                    if sev_overrides:
                        merged["severity_overrides"] = sev_overrides
                else:
                    merged = new_data

            now = _now()
            await conn.execute(
                """INSERT INTO style_profiles (test_type, user_id, profile, sample_count, updated_at, last_data_at)
                   VALUES ($1, $2, $3, $4, $5, $6)
                   ON CONFLICT(test_type, user_id) DO UPDATE SET
                   profile = $3, sample_count = $4, updated_at = $5, last_data_at = $6""",
                test_type, user_id, json.dumps(merged), sample_count, now, created_at or now,
            )

    async def save_edited_text(self, history_id: int | str, edited_text: str, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE history SET edited_text = $1, updated_at = $2 WHERE sync_id = $3 AND user_id = $4",
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

    async def get_no_edit_ratio(
        self, test_type: str, limit: int = 10, user_id: str | None = None,
    ) -> float:
        """Return the fraction of recent copied reports that needed no edits."""
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT edited_text FROM history
                   WHERE user_id = $1 AND test_type = $2 AND copied = true
                   ORDER BY updated_at DESC LIMIT $3""",
                user_id, test_type, limit,
            )
        if not rows:
            return 0.0
        no_edit = sum(1 for r in rows if not r["edited_text"])
        return no_edit / len(rows)

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
        severity_band: str | None = None,
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

        # Severity-band filtering with fallback
        severity_cond = None
        if severity_band == "normal":
            severity_cond = "(severity_score IS NULL OR severity_score < 0.2)"
        elif severity_band == "mild":
            severity_cond = "(severity_score >= 0.2 AND severity_score < 0.5)"
        elif severity_band == "moderate":
            severity_cond = "(severity_score >= 0.5 AND severity_score < 0.8)"
        elif severity_band == "severe":
            severity_cond = "(severity_score >= 0.8)"

        if severity_cond:
            band_where = " WHERE " + " AND ".join(conditions + [severity_cond])
            async with pool.acquire() as conn:
                count_row = await conn.fetchrow(
                    f"SELECT COUNT(*) as cnt FROM history{band_where}",
                    *params,
                )
            if count_row["cnt"] >= 2:
                conditions.append(severity_cond)

        where = " WHERE " + " AND ".join(conditions)
        # Fetch more candidates for recency re-ranking
        fetch_limit = max(limit * 3, 5)
        params.append(fetch_limit)

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT full_response, created_at, liked, copied, quality_rating, edited_text
                    FROM history{where}
                    ORDER BY (CASE WHEN copied = true AND edited_text IS NULL THEN 0 ELSE 1 END),
                             COALESCE(quality_rating, 0) DESC,
                             liked DESC, copied DESC, created_at DESC LIMIT ${idx}""",
                *params,
            )

        # Recency re-ranking: score = approval_signal * 0.6 + recency * 0.4
        from datetime import datetime as _dt, timezone as _tz
        now_dt = _dt.now(_tz.utc)
        scored_rows: list[tuple[float, Any]] = []
        for row in rows:
            approval = 0.0
            if row["copied"] and not row["edited_text"]:
                approval = 1.0
            elif row["quality_rating"] and row["quality_rating"] >= 4:
                approval = 0.9
            elif row["liked"]:
                approval = 0.7
            else:
                approval = 0.5

            recency = 0.2
            try:
                created = row["created_at"]
                if isinstance(created, str):
                    created = _dt.fromisoformat(created.replace("Z", "+00:00"))
                if hasattr(created, 'tzinfo') and created.tzinfo is None:
                    created = created.replace(tzinfo=_tz.utc)
                days = (now_dt - created).days
                if days <= 7:
                    recency = 1.0
                elif days <= 30:
                    recency = 0.5
            except (ValueError, TypeError, AttributeError):
                pass

            score = approval * 0.6 + recency * 0.4
            scored_rows.append((score, row))

        scored_rows.sort(key=lambda x: -x[0])
        ranked_rows = [r for _, r in scored_rows[:limit]]

        examples: list[dict] = []
        for row in ranked_rows:
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

    async def get_preferred_signoff(self, test_type: str, limit: int = 10, user_id: str | None = None) -> str | None:
        """Extract the most common sign-off from copied/liked outputs."""
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT full_response, edited_text FROM history
                   WHERE user_id = $1 AND test_type = $2 AND (liked = true OR copied = true)
                   ORDER BY updated_at DESC LIMIT $3""",
                user_id, test_type, limit,
            )

        closing_re = re.compile(
            r"(?:feel free to|don't hesitate to|please don't hesitate|"
            r"if you have any questions|call (?:our|the|my) office|"
            r"looking forward to|we will discuss|take care|"
            r"best regards|warmly|sincerely|please reach out|"
            r"do not hesitate)[^.!?]*[.!?]?",
            re.IGNORECASE,
        )

        signoff_counts: dict[str, int] = {}
        for row in rows:
            text = row["edited_text"]
            if not text:
                try:
                    fr_raw = row["full_response"]
                    fr = json.loads(fr_raw) if isinstance(fr_raw, str) else fr_raw
                    text = fr.get("explanation", {}).get("overall_summary", "")
                except (json.JSONDecodeError, TypeError):
                    continue
            if not text:
                continue
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            if not paragraphs:
                continue
            match = closing_re.search(paragraphs[-1])
            if match:
                key = match.group(0).strip().lower()
                signoff_counts[key] = signoff_counts.get(key, 0) + 1

        if not signoff_counts:
            return None
        best_key, best_count = max(signoff_counts.items(), key=lambda x: x[1])
        if best_count < 3:
            return None
        # Return original-case version
        for row in rows:
            text = row["edited_text"]
            if not text:
                try:
                    fr_raw = row["full_response"]
                    fr = json.loads(fr_raw) if isinstance(fr_raw, str) else fr_raw
                    text = fr.get("explanation", {}).get("overall_summary", "")
                except (json.JSONDecodeError, TypeError):
                    continue
            if not text:
                continue
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            if paragraphs:
                match = closing_re.search(paragraphs[-1])
                if match and match.group(0).strip().lower() == best_key:
                    return match.group(0).strip()
        return None

    # --- Term Preferences ---

    async def upsert_term_preference(
        self, medical_term: str, test_type: str | None,
        preferred_phrasing: str, keep_technical: bool = False,
        user_id: str | None = None,
    ) -> None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO term_preferences
                   (user_id, medical_term, test_type, preferred_phrasing, keep_technical, count, updated_at)
                   VALUES ($1, $2, $3, $4, $5, 1, $6)
                   ON CONFLICT(user_id, medical_term, test_type) DO UPDATE SET
                   preferred_phrasing = $4, keep_technical = $5,
                   count = term_preferences.count + 1, updated_at = $6""",
                user_id, medical_term.lower(), test_type, preferred_phrasing,
                keep_technical, _now(),
            )

    async def get_term_preferences(
        self, test_type: str | None = None, min_count: int = 3,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            if test_type:
                rows = await conn.fetch(
                    """SELECT medical_term, preferred_phrasing, keep_technical, count
                       FROM term_preferences
                       WHERE user_id = $1 AND (test_type IS NULL OR test_type = $2) AND count >= $3
                       ORDER BY count DESC""",
                    user_id, test_type, min_count,
                )
            else:
                rows = await conn.fetch(
                    """SELECT medical_term, preferred_phrasing, keep_technical, count
                       FROM term_preferences
                       WHERE user_id = $1 AND count >= $2
                       ORDER BY count DESC""",
                    user_id, min_count,
                )
        return [dict(row) for row in rows]

    # --- Conditional Rules ---

    async def upsert_conditional_rule(
        self, test_type: str, severity_band: str, phrase: str,
        pattern_type: str = "general", user_id: str | None = None,
    ) -> None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO conditional_rules
                   (user_id, test_type, severity_band, phrase, pattern_type, count, updated_at)
                   VALUES ($1, $2, $3, $4, $5, 1, $6)
                   ON CONFLICT(user_id, test_type, severity_band, phrase) DO UPDATE SET
                   count = conditional_rules.count + 1,
                   pattern_type = $5, updated_at = $6""",
                user_id, test_type, severity_band, phrase, pattern_type, _now(),
            )

    async def get_conditional_rules(
        self, test_type: str, severity_band: str, min_count: int = 3,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT phrase, pattern_type, count
                   FROM conditional_rules
                   WHERE user_id = $1 AND test_type = $2 AND severity_band = $3 AND count >= $4
                   ORDER BY count DESC LIMIT 5""",
                user_id, test_type, severity_band, min_count,
            )
        return [dict(row) for row in rows]

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
        sync_id = str(uuid.uuid4())
        now = _now()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO templates
                   (user_id, sync_id, name, test_type, tone,
                    structure_instructions, closing_text, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                user_id, sync_id, name, test_type, tone,
                structure_instructions, closing_text, now, now,
            )
            row = await conn.fetchrow(
                "SELECT * FROM templates WHERE sync_id = $1 AND user_id = $2",
                sync_id, user_id,
            )
        return _normalize_row(dict(row))

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
        return [_normalize_row(dict(row)) for row in rows], total

    async def get_template(self, template_id: int | str, user_id: str | None = None) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM templates WHERE sync_id = $1 AND user_id = $2",
                str(template_id), user_id,
            )
        return _normalize_row(dict(row)) if row else None

    async def update_template(self, template_id: int | str, user_id: str | None = None, **kwargs: Any) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT * FROM templates WHERE sync_id = $1 AND user_id = $2",
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
                        "UPDATE templates SET is_default = false WHERE test_type = $1 AND sync_id != $2 AND user_id = $3",
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
                f"UPDATE templates SET {', '.join(set_parts)} WHERE sync_id = ${idx} AND user_id = ${idx+1}",
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
        return _normalize_row(dict(row)) if row else None

    async def delete_template(self, template_id: int | str, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM templates WHERE sync_id = $1 AND user_id = $2",
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
        sync_id = str(uuid.uuid4())
        now = _now()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO letters
                   (user_id, sync_id, prompt, content, letter_type,
                    model_used, input_tokens, output_tokens, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                user_id, sync_id, prompt, content, letter_type,
                model_used, input_tokens, output_tokens, now, now,
            )
        return sync_id

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
        return [_normalize_row(dict(row)) for row in rows], total

    async def update_letter(self, letter_id: int | str, content: str, user_id: str | None = None) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE letters SET content = $1, updated_at = $2 WHERE sync_id = $3 AND user_id = $4",
                content, _now(), str(letter_id), user_id,
            )
            if not result.endswith("1"):
                return None
            row = await conn.fetchrow(
                "SELECT * FROM letters WHERE sync_id = $1 AND user_id = $2",
                str(letter_id), user_id,
            )
        return _normalize_row(dict(row)) if row else None

    async def toggle_letter_liked(self, letter_id: int | str, liked: bool, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE letters SET liked = $1, updated_at = $2 WHERE sync_id = $3 AND user_id = $4",
                liked, _now(), str(letter_id), user_id,
            )
        return result.endswith("1")

    async def get_letter(self, letter_id: int | str, user_id: str | None = None) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM letters WHERE sync_id = $1 AND user_id = $2",
                str(letter_id), user_id,
            )
        return _normalize_row(dict(row)) if row else None

    async def delete_letter(self, letter_id: int | str, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM letters WHERE sync_id = $1 AND user_id = $2",
                str(letter_id), user_id,
            )
        return result.endswith("1")

    # --- Teaching Points ---

    async def create_teaching_point(
        self, text: str, test_type: str | None = None, user_id: str | None = None,
    ) -> dict[str, Any]:
        pool = await _get_pool()
        sync_id = str(uuid.uuid4())
        now = _now()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO teaching_points
                   (user_id, sync_id, test_type, text, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                user_id, sync_id, test_type, text, now, now,
            )
            row = await conn.fetchrow(
                "SELECT * FROM teaching_points WHERE sync_id = $1 AND user_id = $2",
                sync_id, user_id,
            )
        return _normalize_row(dict(row))

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
        return [_normalize_row(dict(row)) for row in rows]

    async def update_teaching_point(
        self, point_id: int | str, text: str | None = None,
        test_type: str | None = "UNSET", user_id: str | None = None,
    ) -> dict[str, Any] | None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM teaching_points WHERE sync_id = $1 AND user_id = $2",
                str(point_id), user_id,
            )
            if row is None:
                return None
            current = _normalize_row(dict(row))
            new_text = text if text is not None else current["text"]
            new_test_type = current["test_type"] if test_type == "UNSET" else test_type
            await conn.execute(
                "UPDATE teaching_points SET text = $1, test_type = $2, updated_at = $3 WHERE sync_id = $4 AND user_id = $5",
                new_text, new_test_type, _now(), str(point_id), user_id,
            )
            updated = await conn.fetchrow(
                "SELECT * FROM teaching_points WHERE sync_id = $1 AND user_id = $2",
                str(point_id), user_id,
            )
        return dict(updated) if updated else None

    async def delete_teaching_point(self, point_id: int | str, user_id: str | None = None) -> bool:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM teaching_points WHERE sync_id = $1 AND user_id = $2",
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
        return [_normalize_row(dict(row)) for row in rows]

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

        # Include practice members' teaching points if sharing is enabled
        if user_id:
            try:
                pool = await _get_pool()
                practice_row = await pool.fetchrow(
                    "SELECT pm.practice_id, p.sharing_enabled "
                    "FROM practice_members pm JOIN practices p ON p.id = pm.practice_id "
                    "WHERE pm.user_id = $1::uuid", user_id,
                )
                if practice_row and practice_row["sharing_enabled"]:
                    practice_id = str(practice_row["practice_id"])
                    if test_type:
                        shared_rows = await pool.fetch(
                            """SELECT tp.id, tp.sync_id, tp.text, tp.test_type,
                                      tp.created_at, tp.updated_at, u.email AS sharer_email
                               FROM teaching_points tp
                               JOIN practice_members pm ON pm.user_id = tp.user_id
                               JOIN users u ON u.id = tp.user_id
                               WHERE pm.practice_id = $1::uuid AND tp.user_id != $2::uuid
                               AND (tp.test_type IS NULL OR tp.test_type = $3)""",
                            practice_id, user_id, test_type,
                        )
                    else:
                        shared_rows = await pool.fetch(
                            """SELECT tp.id, tp.sync_id, tp.text, tp.test_type,
                                      tp.created_at, tp.updated_at, u.email AS sharer_email
                               FROM teaching_points tp
                               JOIN practice_members pm ON pm.user_id = tp.user_id
                               JOIN users u ON u.id = tp.user_id
                               WHERE pm.practice_id = $1::uuid AND tp.user_id != $2::uuid""",
                            practice_id, user_id,
                        )
                    for r in shared_rows:
                        row_dict = _normalize_row(dict(r))
                        row_dict["source"] = "practice"
                        own.append(row_dict)
            except Exception:
                logger.exception("Failed to load practice teaching points for user %s", user_id)

        return own

    async def purge_shared_duplicates_from_own(self, user_id: str | None = None) -> int:
        return 0

    # --- Shared Templates (stubs for web mode) ---

    async def replace_shared_templates(self, rows: list[dict], user_id: str | None = None) -> int:
        return 0

    async def get_shared_template_by_sync_id(self, sync_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        return None

    async def list_shared_templates(self, user_id: str | None = None) -> list[dict[str, Any]]:
        # Include practice members' templates if sharing is enabled
        if user_id:
            try:
                pool = await _get_pool()
                practice_row = await pool.fetchrow(
                    "SELECT pm.practice_id, p.sharing_enabled "
                    "FROM practice_members pm JOIN practices p ON p.id = pm.practice_id "
                    "WHERE pm.user_id = $1::uuid", user_id,
                )
                if practice_row and practice_row["sharing_enabled"]:
                    practice_id = str(practice_row["practice_id"])
                    rows = await pool.fetch(
                        """SELECT t.*, u.email AS sharer_email
                           FROM templates t
                           JOIN practice_members pm ON pm.user_id = t.user_id
                           JOIN users u ON u.id = t.user_id
                           WHERE pm.practice_id = $1::uuid AND t.user_id != $2::uuid
                           ORDER BY t.created_at DESC""",
                        practice_id, user_id,
                    )
                    return [_normalize_row(dict(r)) for r in rows]
            except Exception:
                logger.exception("Failed to load practice templates for user %s", user_id)
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
