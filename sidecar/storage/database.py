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


import re

# Stylistic phrase patterns to extract from liked outputs
# These are non-clinical patterns that reflect communication style
_OPENING_PATTERNS = [
    r"^(I have reviewed|We have reviewed|Your .+ has been reviewed)",
    r"^(Overall,? |In summary,? |To summarize,? )",
    r"^(The good news is|Reassuringly,? |Encouragingly,? )",
    r"^(Thank you for|I wanted to share|I am pleased to report)",
]
_TRANSITION_PATTERNS = [
    r"(On a positive note,? |That said,? |However,? |Additionally,? )",
    r"(It's worth noting|Worth mentioning|Something to be aware of)",
    r"(The reassuring findings|The concerning findings)",
]
_CLOSING_PATTERNS = [
    r"(Please don't hesitate to|Feel free to|If you have any questions)",
    r"(We will discuss|I look forward to|Looking forward to)",
    r"(Take care|Best regards|Warmly)",
]
_SOFTENING_PATTERNS = [
    r"(warrants? discussion|worth discussing|something to discuss)",
    r"(worth mentioning|worth noting|worth being aware of)",
    r"(may be related|could be related|might be associated)",
]


def _extract_stylistic_patterns(text: str) -> dict[str, list[str]]:
    """Extract non-clinical stylistic patterns from liked output text.

    Returns patterns for: openings, transitions, closings, softening language.
    Never extracts clinical content, diagnoses, or measurements.
    """
    patterns: dict[str, list[str]] = {
        "openings": [],
        "transitions": [],
        "closings": [],
        "softening": [],
    }

    # Extract opening patterns (first sentence)
    first_sentence = text.split(".")[0] if "." in text else text[:100]
    for pattern in _OPENING_PATTERNS:
        match = re.search(pattern, first_sentence, re.IGNORECASE)
        if match:
            patterns["openings"].append(match.group(1).strip())

    # Extract transition patterns
    for pattern in _TRANSITION_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches[:3]:  # Limit to 3
            phrase = m.strip() if isinstance(m, str) else m[0].strip()
            if phrase and phrase not in patterns["transitions"]:
                patterns["transitions"].append(phrase)

    # Extract closing patterns (last paragraph)
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if paragraphs:
        last_para = paragraphs[-1]
        for pattern in _CLOSING_PATTERNS:
            match = re.search(pattern, last_para, re.IGNORECASE)
            if match:
                phrase = match.group(1).strip()
                if phrase and phrase not in patterns["closings"]:
                    patterns["closings"].append(phrase)

    # Extract softening language patterns
    for pattern in _SOFTENING_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches[:3]:
            phrase = m.strip() if isinstance(m, str) else m[0].strip()
            if phrase and phrase not in patterns["softening"]:
                patterns["softening"].append(phrase)

    # --- Quantitative style metrics ---
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    if sentences:
        word_counts = [len(s.split()) for s in sentences]
        patterns["avg_sentence_length"] = round(sum(word_counts) / len(word_counts), 1)

        # Fragment usage (sentences < 5 words)
        fragments = sum(1 for wc in word_counts if wc < 5)
        patterns["fragment_count"] = fragments

        # Contraction frequency
        contraction_pattern = r"\b\w+(?:'(?:t|s|re|ve|ll|d|m))\b"
        total_words = sum(word_counts)
        contraction_count = len(re.findall(contraction_pattern, text, re.IGNORECASE))
        if total_words > 0:
            patterns["contraction_rate"] = round(contraction_count / total_words, 2)

    return patterns


def _severity_band(score: float | None) -> str:
    """Map a severity score (0.0-1.0) to a named band."""
    if score is None or score < 0.2:
        return "normal"
    elif score < 0.5:
        return "mild"
    elif score < 0.8:
        return "moderate"
    else:
        return "severe"


def _compute_adaptive_alpha(
    base_alpha: float, created_at: str, last_updated: str,
) -> float:
    """Return an adaptive alpha based on recency of data.

    - <= 1 day since last update: alpha * 1.5 (capped at 0.6)
    - 1-7 days: base alpha
    - > 7 days: alpha * 0.7 (floor 0.1)
    """
    try:
        from datetime import datetime, timezone
        # Parse ISO 8601 timestamps
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        updated = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
        delta = abs((created - updated).total_seconds()) / 86400  # days
        if delta <= 1:
            return min(base_alpha * 1.5, 0.6)
        elif delta <= 7:
            return base_alpha
        else:
            return max(base_alpha * 0.7, 0.1)
    except (ValueError, TypeError):
        return base_alpha


def _merge_profile(
    existing: dict[str, Any], new_data: dict[str, Any], alpha: float,
) -> dict[str, Any]:
    """Merge new style data into existing profile using EMA for numeric fields
    and union for list fields."""
    merged = dict(existing)
    for key, new_val in new_data.items():
        if key not in merged:
            merged[key] = new_val
            continue
        old_val = merged[key]
        if isinstance(new_val, (int, float)) and isinstance(old_val, (int, float)):
            # Exponential moving average
            merged[key] = round(old_val * (1 - alpha) + new_val * alpha, 3)
        elif isinstance(new_val, list) and isinstance(old_val, list):
            # Union, keeping order, max 20 items
            seen = set(old_val)
            combined = list(old_val)
            for item in new_val:
                if item not in seen:
                    combined.append(item)
                    seen.add(item)
            merged[key] = combined[:20]
        else:
            merged[key] = new_val
    return merged


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
    liked INTEGER NOT NULL DEFAULT 0,
    tone_preference INTEGER,
    detail_preference INTEGER,
    copied INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT,
    sync_id TEXT,
    edited_text TEXT,
    quality_rating INTEGER,
    quality_note TEXT,
    tone_used INTEGER,
    detail_used INTEGER,
    literacy_used TEXT,
    was_edited INTEGER NOT NULL DEFAULT 0
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
    is_default INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS shared_teaching_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_id TEXT NOT NULL UNIQUE,
    text TEXT NOT NULL,
    test_type TEXT,
    sharer_user_id TEXT NOT NULL,
    sharer_email TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS shared_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    test_type TEXT,
    tone TEXT,
    structure_instructions TEXT,
    closing_text TEXT,
    sharer_user_id TEXT NOT NULL,
    sharer_email TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT
);
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
                "ALTER TABLE history ADD COLUMN edited_text TEXT",
                "ALTER TABLE templates ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE history ADD COLUMN quality_rating INTEGER",
                "ALTER TABLE history ADD COLUMN quality_note TEXT",
                "ALTER TABLE history ADD COLUMN tone_used INTEGER",
                "ALTER TABLE history ADD COLUMN detail_used INTEGER",
                "ALTER TABLE history ADD COLUMN literacy_used TEXT",
                "ALTER TABLE history ADD COLUMN was_edited INTEGER NOT NULL DEFAULT 0",
                "CREATE TABLE IF NOT EXISTS style_profiles (test_type TEXT PRIMARY KEY, profile TEXT NOT NULL, sample_count INTEGER NOT NULL DEFAULT 0, updated_at TEXT)",
                "ALTER TABLE history ADD COLUMN severity_score REAL",
                "ALTER TABLE style_profiles ADD COLUMN last_data_at TEXT",
                # New tables for personalization features
                """CREATE TABLE IF NOT EXISTS term_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    medical_term TEXT NOT NULL,
                    test_type TEXT,
                    preferred_phrasing TEXT NOT NULL,
                    keep_technical INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT 'edit',
                    count INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT,
                    UNIQUE(medical_term, test_type)
                )""",
                """CREATE TABLE IF NOT EXISTS conditional_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_type TEXT NOT NULL,
                    severity_band TEXT NOT NULL,
                    phrase TEXT NOT NULL,
                    pattern_type TEXT NOT NULL DEFAULT 'general',
                    count INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT,
                    UNIQUE(test_type, severity_band, phrase)
                )""",
                """CREATE TABLE IF NOT EXISTS detection_corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    detected_type TEXT NOT NULL,
                    corrected_type TEXT NOT NULL,
                    report_title TEXT,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                )""",
                """CREATE INDEX IF NOT EXISTS idx_detection_corrections_types
                    ON detection_corrections(detected_type, corrected_type)""",
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

            # Backfill severity_score from full_response JSON
            try:
                rows_no_sev = conn.execute(
                    "SELECT id, full_response FROM history WHERE severity_score IS NULL"
                ).fetchall()
                for row in rows_no_sev:
                    try:
                        fr = json.loads(row["full_response"]) if isinstance(row["full_response"], str) else row["full_response"]
                        sev = fr.get("severity_score") if isinstance(fr, dict) else None
                        if sev is not None:
                            conn.execute(
                                "UPDATE history SET severity_score = ? WHERE id = ?",
                                (float(sev), row["id"]),
                            )
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
                conn.commit()
            except sqlite3.OperationalError:
                pass

            # Indexes that depend on migrated columns
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_liked ON history(liked)"
            )
            conn.commit()

            # Deduplicate and create unique indexes on sync_id to prevent sync duplicates
            for tbl in ("history", "letters", "templates", "teaching_points"):
                try:
                    # Delete duplicates, keeping the row with the lowest id (oldest)
                    conn.execute(f"""
                        DELETE FROM {tbl}
                        WHERE id NOT IN (
                            SELECT MIN(id) FROM {tbl}
                            WHERE sync_id IS NOT NULL
                            GROUP BY sync_id
                        ) AND sync_id IS NOT NULL
                    """)
                    conn.commit()
                    # Create unique index
                    conn.execute(
                        f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{tbl}_sync_id ON {tbl}(sync_id) WHERE sync_id IS NOT NULL"
                    )
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # Index already exists or other issue

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
        severity_score: float | None = None,
    ) -> dict[str, Any]:
        conn = self._get_conn()
        try:
            sid = str(uuid.uuid4())
            now = _now()
            cursor = conn.execute(
                """INSERT INTO history (test_type, test_type_display, filename, summary, full_response, tone_preference, detail_preference, sync_id, updated_at, severity_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    severity_score,
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

    def rate_history(self, history_id: int, rating: int, note: str | None = None) -> bool:
        """Save a quality rating (1-5) and optional note for a history entry."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "UPDATE history SET quality_rating = ?, quality_note = ?, updated_at = ? WHERE id = ?",
                (rating, note, _now(), history_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_recent_feedback(
        self, test_type: str, limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Fetch recent quality notes with rating <= 3 for feedback analysis."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT quality_rating, quality_note FROM history
                   WHERE test_type = ? AND quality_rating IS NOT NULL
                     AND quality_rating <= 3 AND quality_note IS NOT NULL
                     AND quality_note != ''
                   ORDER BY updated_at DESC LIMIT ?""",
                (test_type, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def save_history_settings_used(
        self, history_id: int, tone: int | None, detail: int | None,
        literacy: str | None, was_edited: bool = False,
    ) -> bool:
        """Record which settings were used to generate this report.

        When tone/detail/literacy are None, only was_edited is updated
        (avoids overwriting previously stored values).
        """
        conn = self._get_conn()
        try:
            if tone is None and detail is None and literacy is None:
                # Only update was_edited flag
                cursor = conn.execute(
                    "UPDATE history SET was_edited = ?, updated_at = ? WHERE id = ?",
                    (1 if was_edited else 0, _now(), history_id),
                )
            else:
                cursor = conn.execute(
                    """UPDATE history SET tone_used = ?, detail_used = ?,
                       literacy_used = ?, was_edited = ?, updated_at = ?
                       WHERE id = ?""",
                    (tone, detail, literacy, 1 if was_edited else 0, _now(), history_id),
                )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_optimal_settings(self, test_type: str, min_samples: int = 5) -> dict[str, Any] | None:
        """Find tone/detail settings with the lowest edit rate for a test type."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT tone_used, detail_used, COUNT(*) as cnt,
                          SUM(CASE WHEN was_edited = 1 THEN 1 ELSE 0 END) as edit_count
                   FROM history
                   WHERE test_type = ? AND tone_used IS NOT NULL AND detail_used IS NOT NULL
                   GROUP BY tone_used, detail_used
                   HAVING COUNT(*) >= ?
                   ORDER BY (CAST(SUM(CASE WHEN was_edited = 1 THEN 1 ELSE 0 END) AS REAL) / COUNT(*))
                   LIMIT 1""",
                (test_type, min_samples),
            ).fetchall()
            if not rows:
                return None
            r = dict(rows[0])
            return {
                "tone": r["tone_used"],
                "detail": r["detail_used"],
                "sample_count": r["cnt"],
                "edit_rate": round(r["edit_count"] / r["cnt"], 2),
            }
        finally:
            conn.close()

    def get_style_profile(self, test_type: str, severity_band: str | None = None) -> dict[str, Any] | None:
        """Get the persistent style profile for a test type.

        If severity_band is given, merge band-specific overrides from
        profile.severity_overrides[band] onto the base profile.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT profile, sample_count FROM style_profiles WHERE test_type = ?",
                (test_type,),
            ).fetchone()
            if not row:
                return None
            profile = json.loads(row["profile"])
            # Apply severity-band overrides if present
            if severity_band and "severity_overrides" in profile:
                overrides = profile["severity_overrides"].get(severity_band, {})
                if overrides:
                    merged = dict(profile)
                    merged.pop("severity_overrides", None)
                    merged.update(overrides)
                    return {"profile": merged, "sample_count": row["sample_count"]}
            return {
                "profile": profile,
                "sample_count": row["sample_count"],
            }
        except Exception:
            return None
        finally:
            conn.close()

    def update_style_profile(
        self, test_type: str, new_data: dict[str, Any], alpha: float = 0.3,
        severity_band: str | None = None, created_at: str | None = None,
    ) -> None:
        """Update the style profile using exponential moving average.

        *alpha* controls how quickly the profile adapts (0 = never, 1 = replace).
        If *severity_band* is given, writes to profile.severity_overrides[band].
        If *created_at* is given, alpha is adjusted for recency (Phase D).
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT profile, sample_count, updated_at AS last_updated FROM style_profiles WHERE test_type = ?",
                (test_type,),
            ).fetchone()

            # Adaptive alpha based on recency
            effective_alpha = alpha
            if created_at and row and row["last_updated"]:
                effective_alpha = _compute_adaptive_alpha(alpha, created_at, row["last_updated"])

            if row:
                existing = json.loads(row["profile"])
                sample_count = row["sample_count"] + 1
            else:
                existing = {}
                sample_count = 1

            if severity_band:
                # Write to severity_overrides sub-dict
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
                    # Preserve severity_overrides during base merge
                    sev_overrides = existing.pop("severity_overrides", None)
                    merged = _merge_profile(existing, new_data, effective_alpha)
                    if sev_overrides:
                        merged["severity_overrides"] = sev_overrides
                else:
                    merged = new_data

            now = _now()
            conn.execute(
                """INSERT INTO style_profiles (test_type, profile, sample_count, updated_at, last_data_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(test_type) DO UPDATE SET
                   profile = excluded.profile, sample_count = excluded.sample_count,
                   updated_at = excluded.updated_at, last_data_at = excluded.last_data_at""",
                (test_type, json.dumps(merged), sample_count, now, created_at or now),
            )
            conn.commit()
        finally:
            conn.close()

    def save_edited_text(self, history_id: int, edited_text: str) -> bool:
        """Save the doctor's edited version of the explanation text."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "UPDATE history SET edited_text = ?, updated_at = ? WHERE id = ?",
                (edited_text, _now(), history_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_recent_edits(
        self, test_type: str, limit: int = 3
    ) -> list[dict[str, Any]]:
        """Analyze recent doctor edits to find structural patterns.

        Returns structural metadata ONLY (length change, paragraph change) —
        never clinical content — to guide future output without biasing
        the LLM with prior diagnoses.
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT full_response, edited_text FROM history
                   WHERE test_type = ? AND edited_text IS NOT NULL
                   ORDER BY updated_at DESC LIMIT ?""",
                (test_type, limit),
            ).fetchall()

            edits: list[dict[str, Any]] = []
            for row in rows:
                try:
                    if not row["edited_text"]:
                        continue

                    full_response = json.loads(row["full_response"])
                    original = full_response.get("explanation", {}).get("overall_summary", "")
                    edited = row["edited_text"]

                    if not original:
                        continue

                    # Calculate structural metadata
                    original_len = len(original)
                    edited_len = len(edited)
                    length_change_pct = ((edited_len - original_len) / original_len * 100) if original_len > 0 else 0

                    original_paragraphs = len([p for p in original.split("\n\n") if p.strip()])
                    edited_paragraphs = len([p for p in edited.split("\n\n") if p.strip()])
                    paragraph_change = edited_paragraphs - original_paragraphs

                    edits.append({
                        "length_change_pct": round(length_change_pct, 1),
                        "paragraph_change": paragraph_change,
                        "shorter": edited_len < original_len,
                        "longer": edited_len > original_len,
                    })
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue

            return edits
        finally:
            conn.close()

    def get_no_edit_ratio(self, test_type: str, limit: int = 10) -> float:
        """Return the fraction of recent copied reports that needed no edits.

        Looks at the most recent `limit` reports that were copied. Returns the
        ratio of those that have no edited_text (i.e., physician accepted as-is).
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT edited_text FROM history
                   WHERE test_type = ? AND copied = 1
                   ORDER BY updated_at DESC LIMIT ?""",
                (test_type, limit),
            ).fetchall()
            if not rows:
                return 0.0
            no_edit = sum(1 for r in rows if not r["edited_text"])
            return no_edit / len(rows)
        finally:
            conn.close()

    def get_learned_phrases(self, test_type: str | None = None, limit: int = 10) -> list[str]:
        """Extract common phrases that doctors add when editing outputs.

        Analyzes edited text to find phrases not present in the original output
        that appear across multiple edits, indicating preferred phrasing.
        Returns up to `limit` learned phrases.
        """
        import re

        conn = self._get_conn()
        try:
            if test_type:
                rows = conn.execute(
                    """SELECT full_response, edited_text FROM history
                       WHERE test_type = ? AND edited_text IS NOT NULL
                       ORDER BY updated_at DESC LIMIT 20""",
                    (test_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT full_response, edited_text FROM history
                       WHERE edited_text IS NOT NULL
                       ORDER BY updated_at DESC LIMIT 20""",
                ).fetchall()

            # Collect phrases added in edits
            added_phrases: dict[str, int] = {}

            for row in rows:
                try:
                    if not row["edited_text"]:
                        continue

                    full_response = json.loads(row["full_response"])
                    original = full_response.get("explanation", {}).get("overall_summary", "")
                    edited = row["edited_text"]

                    if not original or not edited:
                        continue

                    # Find sentences/phrases in edited that aren't in original
                    original_lower = original.lower()

                    # Split edited text into sentences
                    sentences = re.split(r'(?<=[.!?])\s+', edited)
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if len(sentence) < 10 or len(sentence) > 150:
                            continue

                        # Check if this sentence (or close variant) exists in original
                        sentence_lower = sentence.lower()
                        if sentence_lower not in original_lower:
                            # This is an added phrase - count it
                            # Normalize for counting
                            normalized = sentence_lower[:80]  # Truncate for matching
                            added_phrases[normalized] = added_phrases.get(normalized, 0) + 1

                except (json.JSONDecodeError, TypeError, KeyError):
                    continue

            # Return phrases that appear more than once (learned patterns)
            frequent_phrases = [
                phrase for phrase, count in sorted(
                    added_phrases.items(), key=lambda x: -x[1]
                )
                if count >= 2
            ][:limit]

            return frequent_phrases
        finally:
            conn.close()

    def get_preferred_signoff(self, test_type: str, limit: int = 10) -> str | None:
        """Extract the most common sign-off from copied/liked outputs.

        Prefers edited_text (doctor's actual words) over generated text.
        Returns the sign-off only if it appears >= 3 times.
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT full_response, edited_text FROM history
                   WHERE test_type = ? AND (liked = 1 OR copied = 1)
                   ORDER BY updated_at DESC LIMIT ?""",
                (test_type, limit),
            ).fetchall()

            signoff_counts: dict[str, int] = {}
            closing_re = re.compile(
                r"(?:feel free to|don't hesitate to|please don't hesitate|"
                r"if you have any questions|call (?:our|the|my) office|"
                r"looking forward to|we will discuss|take care|"
                r"best regards|warmly|sincerely|please reach out|"
                r"do not hesitate)[^.!?]*[.!?]?",
                re.IGNORECASE,
            )

            for row in rows:
                text = row["edited_text"]
                if not text:
                    try:
                        fr = json.loads(row["full_response"]) if isinstance(row["full_response"], str) else row["full_response"]
                        text = fr.get("explanation", {}).get("overall_summary", "")
                    except (json.JSONDecodeError, TypeError):
                        continue
                if not text:
                    continue

                # Get last paragraph
                paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                if not paragraphs:
                    continue
                last_para = paragraphs[-1]
                match = closing_re.search(last_para)
                if match:
                    signoff = match.group(0).strip()
                    # Normalize to lowercase key for counting
                    key = signoff.lower()
                    signoff_counts[key] = signoff_counts.get(key, 0) + 1

            if not signoff_counts:
                return None

            best_key, best_count = max(signoff_counts.items(), key=lambda x: x[1])
            if best_count >= 3:
                # Return the original-case version by re-scanning
                for row in rows:
                    text = row["edited_text"]
                    if not text:
                        try:
                            fr = json.loads(row["full_response"]) if isinstance(row["full_response"], str) else row["full_response"]
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
            return None
        finally:
            conn.close()

    def get_prior_measurements(
        self, test_type: str, limit: int = 3
    ) -> list[dict[str, Any]]:
        """Fetch prior measurements for the same test type for trend comparison.

        Returns a list of dicts with:
        - date: ISO date string (e.g., "2025-01-15")
        - measurements: list of {abbreviation, value, unit, status}
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT created_at, full_response FROM history
                   WHERE test_type = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (test_type, limit),
            ).fetchall()

            results: list[dict[str, Any]] = []
            for row in rows:
                try:
                    full_response = json.loads(row["full_response"])
                    parsed_report = full_response.get("parsed_report", {})
                    measurements = parsed_report.get("measurements", [])

                    # Extract date portion from ISO timestamp
                    created_at = row["created_at"]
                    date_str = created_at[:10] if created_at else "Unknown"

                    # Extract only the essential measurement info
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
        finally:
            conn.close()

    def get_liked_examples(
        self,
        limit: int = 2,
        test_type: str | None = None,
        tone_preference: int | None = None,
        detail_preference: int | None = None,
        severity_band: str | None = None,
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
                band_conditions = conditions + [severity_cond]
                band_where = " WHERE " + " AND ".join(band_conditions)
                count_row = conn.execute(
                    f"SELECT COUNT(*) as cnt FROM history{band_where}",
                    params,
                ).fetchone()
                if count_row["cnt"] >= 2:
                    conditions.append(severity_cond)

            where_clause = " WHERE " + " AND ".join(conditions)
            # Fetch more candidates for recency re-ranking, then return top `limit`
            fetch_limit = max(limit * 3, 5)
            params.append(fetch_limit)
            rows = conn.execute(
                f"""SELECT full_response, created_at, liked, copied, quality_rating, edited_text
                    FROM history{where_clause}
                    ORDER BY (CASE WHEN copied = 1 AND edited_text IS NULL THEN 0 ELSE 1 END),
                             COALESCE(quality_rating, 0) DESC,
                             liked DESC, copied DESC, created_at DESC LIMIT ?""",
                params,
            ).fetchall()

            # Recency re-ranking: score = approval_signal * 0.6 + recency * 0.4
            from datetime import datetime, timezone
            now_dt = datetime.now(timezone.utc)
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
                    created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
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
                    full_response = json.loads(row["full_response"])
                    explanation = full_response.get("explanation", {})
                    overall_summary = explanation.get("overall_summary", "")
                    key_findings = explanation.get("key_findings", [])
                    if not overall_summary:
                        continue
                    # Extract ONLY structural/style metadata — never
                    # include clinical content, which can prime the LLM
                    # to reproduce prior diagnoses on unrelated reports.
                    paragraphs = [p for p in overall_summary.split("\n\n") if p.strip()]
                    sentences = overall_summary.replace("\n", " ").split(". ")
                    # Extract stylistic phrases (non-clinical patterns)
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
        finally:
            conn.close()

    # --- Term Preferences ---

    def upsert_term_preference(
        self, medical_term: str, test_type: str | None,
        preferred_phrasing: str, keep_technical: bool = False,
    ) -> None:
        """Insert or increment count for a term preference."""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO term_preferences
                   (medical_term, test_type, preferred_phrasing, keep_technical, count, updated_at)
                   VALUES (?, ?, ?, ?, 1, ?)
                   ON CONFLICT(medical_term, test_type) DO UPDATE SET
                   preferred_phrasing = excluded.preferred_phrasing,
                   keep_technical = excluded.keep_technical,
                   count = count + 1,
                   updated_at = excluded.updated_at""",
                (medical_term.lower(), test_type, preferred_phrasing, 1 if keep_technical else 0, _now()),
            )
            conn.commit()
        finally:
            conn.close()

    def get_term_preferences(
        self, test_type: str | None = None, min_count: int = 3,
    ) -> list[dict[str, Any]]:
        """Return term preferences with count >= min_count."""
        conn = self._get_conn()
        try:
            if test_type:
                rows = conn.execute(
                    """SELECT medical_term, preferred_phrasing, keep_technical, count
                       FROM term_preferences
                       WHERE (test_type IS NULL OR test_type = ?) AND count >= ?
                       ORDER BY count DESC""",
                    (test_type, min_count),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT medical_term, preferred_phrasing, keep_technical, count
                       FROM term_preferences WHERE count >= ?
                       ORDER BY count DESC""",
                    (min_count,),
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # --- Conditional Rules ---

    def upsert_conditional_rule(
        self, test_type: str, severity_band: str, phrase: str,
        pattern_type: str = "general",
    ) -> None:
        """Insert or increment count for a conditional rule."""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO conditional_rules
                   (test_type, severity_band, phrase, pattern_type, count, updated_at)
                   VALUES (?, ?, ?, ?, 1, ?)
                   ON CONFLICT(test_type, severity_band, phrase) DO UPDATE SET
                   count = count + 1,
                   pattern_type = excluded.pattern_type,
                   updated_at = excluded.updated_at""",
                (test_type, severity_band, phrase, pattern_type, _now()),
            )
            conn.commit()
        finally:
            conn.close()

    def get_conditional_rules(
        self, test_type: str, severity_band: str, min_count: int = 3,
    ) -> list[dict[str, Any]]:
        """Return conditional rules for a test type and severity band."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT phrase, pattern_type, count
                   FROM conditional_rules
                   WHERE test_type = ? AND severity_band = ? AND count >= ?
                   ORDER BY count DESC LIMIT 5""",
                (test_type, severity_band, min_count),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # --- Templates ---

    @staticmethod
    def _normalize_template_row(row: dict[str, Any]) -> dict[str, Any]:
        """Add test_types list by parsing the test_type column (JSON array or bare string)."""
        from api.template_models import normalize_test_type_field
        row["test_types"] = normalize_test_type_field(row.get("test_type"))
        return row

    def create_template(
        self,
        name: str,
        test_type: str | None = None,
        test_types: list[str] | None = None,
        tone: str | None = None,
        structure_instructions: str | None = None,
        closing_text: str | None = None,
    ) -> dict[str, Any]:
        # If test_types list provided, serialize to JSON for the test_type column
        if test_types:
            test_type = json.dumps(test_types)
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
            return [self._normalize_template_row(dict(row)) for row in rows], total
        finally:
            conn.close()

    def get_template(self, template_id: int) -> dict[str, Any] | None:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM templates WHERE id = ?", (template_id,)
            ).fetchone()
            return self._normalize_template_row(dict(row)) if row else None
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

            allowed = {"name", "test_type", "tone", "structure_instructions", "closing_text", "is_default"}
            updates = {k: v for k, v in kwargs.items() if k in allowed}
            if not updates:
                return self._normalize_template_row(dict(existing))

            # If setting as default, clear defaults for each type in the JSON array
            if updates.get("is_default"):
                test_type_raw = updates.get("test_type", existing["test_type"])
                if test_type_raw:
                    from api.template_models import normalize_test_type_field
                    types_list = normalize_test_type_field(test_type_raw) or []
                    for t in types_list:
                        conn.execute(
                            """UPDATE templates SET is_default = 0
                               WHERE id != ? AND is_default = 1 AND EXISTS (
                                 SELECT 1 FROM json_each(
                                   CASE WHEN test_type LIKE '[%' THEN test_type ELSE json_array(test_type) END
                                 ) WHERE value = ?
                               )""",
                            (template_id, t),
                        )

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

    def get_default_template_for_type(self, test_type: str) -> dict[str, Any] | None:
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT * FROM templates WHERE is_default = 1 AND EXISTS (
                     SELECT 1 FROM json_each(
                       CASE WHEN test_type LIKE '[%' THEN test_type ELSE json_array(test_type) END
                     ) WHERE value = ?
                   ) LIMIT 1""",
                (test_type,),
            ).fetchone()
            return self._normalize_template_row(dict(row)) if row else None
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


    def list_history_test_types(self) -> list[dict[str, str]]:
        """Return distinct test types from the history table."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT DISTINCT test_type, test_type_display FROM history ORDER BY test_type_display"
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # --- Shared Teaching Points ---

    def replace_shared_teaching_points(self, rows: list[dict]) -> int:
        """Full-replace: delete all cached shared teaching points, re-insert from sync."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM shared_teaching_points")
            count = 0
            for row in rows:
                conn.execute(
                    """INSERT INTO shared_teaching_points
                       (sync_id, text, test_type, sharer_user_id, sharer_email, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row.get("sync_id", ""),
                        row.get("text", ""),
                        row.get("test_type"),
                        row.get("sharer_user_id", ""),
                        row.get("sharer_email", ""),
                        row.get("created_at"),
                        row.get("updated_at"),
                    ),
                )
                count += 1
            conn.commit()
            return count
        finally:
            conn.close()

    def list_shared_teaching_points(
        self, test_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return shared teaching points, optionally filtered by test_type (includes global).

        Excludes shared points whose sync_id already exists in the user's own
        teaching_points table to avoid duplicates when a sharer's content
        overlaps with the user's own library.
        """
        conn = self._get_conn()
        try:
            if test_type:
                rows = conn.execute(
                    """SELECT * FROM shared_teaching_points
                       WHERE (test_type IS NULL OR test_type = ?)
                         AND sync_id NOT IN (SELECT sync_id FROM teaching_points WHERE sync_id IS NOT NULL)
                       ORDER BY created_at DESC""",
                    (test_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM shared_teaching_points
                       WHERE sync_id NOT IN (SELECT sync_id FROM teaching_points WHERE sync_id IS NOT NULL)
                       ORDER BY created_at DESC""",
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def list_all_teaching_points_for_prompt(
        self, test_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Union of own + shared teaching points. Each dict has 'source' field ('own' or sharer email)."""
        own = self.list_teaching_points(test_type=test_type)
        for tp in own:
            tp["source"] = "own"
        shared = self.list_shared_teaching_points(test_type=test_type)
        for tp in shared:
            tp["source"] = tp.get("sharer_email", "shared")
        return own + shared

    def purge_shared_duplicates_from_own(self) -> int:
        """Remove rows from teaching_points whose sync_id also exists in
        shared_teaching_points.  These are shared content that was incorrectly
        merged into the user's own table during sync."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """DELETE FROM teaching_points
                   WHERE sync_id IN (
                       SELECT sync_id FROM shared_teaching_points
                       WHERE sync_id IS NOT NULL
                   )"""
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    # --- Shared Templates ---

    def replace_shared_templates(self, rows: list[dict]) -> int:
        """Full-replace: delete all cached shared templates, re-insert from sync."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM shared_templates")
            count = 0
            for row in rows:
                conn.execute(
                    """INSERT INTO shared_templates
                       (sync_id, name, test_type, tone, structure_instructions, closing_text,
                        sharer_user_id, sharer_email, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row.get("sync_id", ""),
                        row.get("name", ""),
                        row.get("test_type"),
                        row.get("tone"),
                        row.get("structure_instructions"),
                        row.get("closing_text"),
                        row.get("sharer_user_id", ""),
                        row.get("sharer_email", ""),
                        row.get("created_at"),
                        row.get("updated_at"),
                    ),
                )
                count += 1
            conn.commit()
            return count
        finally:
            conn.close()

    def get_shared_template_by_sync_id(self, sync_id: str) -> dict[str, Any] | None:
        """Look up a single shared template by its sync_id."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM shared_templates WHERE sync_id = ?",
                (sync_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_shared_templates(self) -> list[dict[str, Any]]:
        """Return all cached shared templates."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM shared_templates ORDER BY created_at DESC",
            ).fetchall()
            return [dict(row) for row in rows]
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
