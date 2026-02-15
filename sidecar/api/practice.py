"""Practice (organization) management endpoints.

Web-only (REQUIRE_AUTH) — these endpoints need a valid JWT.
Allows practice admins to invite/manage members, control sharing,
and view aggregated usage across all practice members.
"""

import logging
import os
import secrets
import string

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "").lower() == "true"

router = APIRouter(prefix="/practice", tags=["practice"])

# Safe alphabet for join codes: uppercase + digits, minus ambiguous chars
_SAFE_ALPHABET = "".join(
    c for c in string.ascii_uppercase + string.digits
    if c not in "0O1IL"
)


def _generate_join_code(length: int = 8) -> str:
    """Generate a random join code from the safe alphabet."""
    return "".join(secrets.choice(_SAFE_ALPHABET) for _ in range(length))


def _get_user_id(request: Request) -> str:
    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return uid


async def _get_pool():
    from storage.pg_database import _get_pool
    return await _get_pool()


async def _require_practice_admin(request: Request) -> tuple[str, str]:
    """Return (practice_id, user_id) or raise 403."""
    user_id = _get_user_id(request)
    pool = await _get_pool()
    row = await pool.fetchrow(
        "SELECT practice_id, role FROM practice_members WHERE user_id = $1::uuid",
        user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="You are not in a practice.")
    if row["role"] != "admin":
        raise HTTPException(status_code=403, detail="Practice admin access required.")
    return str(row["practice_id"]), user_id


def _invalidate_practice_cache(user_id: str) -> None:
    """Remove user from practice context cache so it refreshes on next request."""
    from api.auth import invalidate_practice_cache
    invalidate_practice_cache(user_id)


# ---------------------------------------------------------------------------
# Create / Join / Leave
# ---------------------------------------------------------------------------


@router.post("/create")
async def create_practice(request: Request):
    """Create a new practice. Caller becomes admin."""
    user_id = _get_user_id(request)
    pool = await _get_pool()

    # Check user isn't already in a practice
    existing = await pool.fetchrow(
        "SELECT practice_id FROM practice_members WHERE user_id = $1::uuid",
        user_id,
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="You are already in a practice. Leave it first to create a new one.",
        )

    try:
        body = await request.json()
    except Exception:
        body = {}
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Practice name is required.")
    specialty = (body.get("specialty") or "").strip() or None

    # Generate unique join code (retry on collision)
    for _ in range(10):
        join_code = _generate_join_code()
        conflict = await pool.fetchrow(
            "SELECT id FROM practices WHERE join_code = $1", join_code,
        )
        if not conflict:
            break
    else:
        raise HTTPException(status_code=500, detail="Failed to generate unique join code.")

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """INSERT INTO practices (name, specialty, join_code)
                   VALUES ($1, $2, $3) RETURNING *""",
                name, specialty, join_code,
            )
            practice_id = str(row["id"])
            await conn.execute(
                """INSERT INTO practice_members (practice_id, user_id, role)
                   VALUES ($1::uuid, $2::uuid, 'admin')""",
                practice_id, user_id,
            )

    _invalidate_practice_cache(user_id)

    return {
        "practice": {
            "id": practice_id,
            "name": row["name"],
            "specialty": row["specialty"],
            "join_code": row["join_code"],
            "sharing_enabled": row["sharing_enabled"],
            "created_at": str(row["created_at"]),
        },
        "role": "admin",
        "member_count": 1,
    }


@router.get("/mine")
async def get_my_practice(request: Request):
    """Get the current user's practice info, or null if not in one."""
    user_id = _get_user_id(request)
    pool = await _get_pool()

    row = await pool.fetchrow("SELECT * FROM get_user_practice($1::uuid)", user_id)
    if not row:
        return None

    return {
        "practice": {
            "id": str(row["practice_id"]),
            "name": row["practice_name"],
            "specialty": row["specialty"],
            "join_code": row["join_code"],
            "sharing_enabled": row["sharing_enabled"],
        },
        "role": row["role"],
        "member_count": row["member_count"],
    }


@router.post("/join")
async def join_practice(request: Request):
    """Join a practice via join code."""
    user_id = _get_user_id(request)
    pool = await _get_pool()

    # Check not already in a practice
    existing = await pool.fetchrow(
        "SELECT practice_id FROM practice_members WHERE user_id = $1::uuid",
        user_id,
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="You are already in a practice. Leave it first to join another.",
        )

    try:
        body = await request.json()
    except Exception:
        body = {}
    join_code = (body.get("join_code") or "").strip().upper()
    if not join_code:
        raise HTTPException(status_code=400, detail="Join code is required.")

    practice = await pool.fetchrow(
        "SELECT id, name, specialty, join_code, sharing_enabled FROM practices WHERE join_code = $1",
        join_code,
    )
    if not practice:
        raise HTTPException(status_code=404, detail="Invalid join code.")

    practice_id = str(practice["id"])
    await pool.execute(
        """INSERT INTO practice_members (practice_id, user_id, role)
           VALUES ($1::uuid, $2::uuid, 'member')""",
        practice_id, user_id,
    )

    _invalidate_practice_cache(user_id)

    member_count = await pool.fetchval(
        "SELECT COUNT(*) FROM practice_members WHERE practice_id = $1::uuid",
        practice_id,
    )

    return {
        "practice": {
            "id": practice_id,
            "name": practice["name"],
            "specialty": practice["specialty"],
            "join_code": practice["join_code"],
            "sharing_enabled": practice["sharing_enabled"],
        },
        "role": "member",
        "member_count": member_count,
    }


@router.post("/leave")
async def leave_practice(request: Request):
    """Leave current practice. Sole admin cannot leave."""
    user_id = _get_user_id(request)
    pool = await _get_pool()

    membership = await pool.fetchrow(
        "SELECT practice_id, role FROM practice_members WHERE user_id = $1::uuid",
        user_id,
    )
    if not membership:
        raise HTTPException(status_code=404, detail="You are not in a practice.")

    practice_id = str(membership["practice_id"])

    # If admin, ensure there's another admin
    if membership["role"] == "admin":
        admin_count = await pool.fetchval(
            "SELECT COUNT(*) FROM practice_members WHERE practice_id = $1::uuid AND role = 'admin'",
            practice_id,
        )
        if admin_count <= 1:
            raise HTTPException(
                status_code=409,
                detail="You are the only admin. Promote another member before leaving.",
            )

    await pool.execute(
        "DELETE FROM practice_members WHERE user_id = $1::uuid",
        user_id,
    )

    _invalidate_practice_cache(user_id)

    # If no members remain, delete the practice
    remaining = await pool.fetchval(
        "SELECT COUNT(*) FROM practice_members WHERE practice_id = $1::uuid",
        practice_id,
    )
    if remaining == 0:
        await pool.execute("DELETE FROM practices WHERE id = $1::uuid", practice_id)

    return {"left": True}


# ---------------------------------------------------------------------------
# Member Management (admin only)
# ---------------------------------------------------------------------------


@router.get("/members")
async def list_members(request: Request):
    """List all members with usage stats. Admin only."""
    practice_id, _ = await _require_practice_admin(request)
    pool = await _get_pool()

    rows = await pool.fetch(
        "SELECT * FROM list_practice_members($1::uuid)", practice_id,
    )
    return [
        {
            "user_id": str(r["user_id"]),
            "email": r["email"],
            "role": r["role"],
            "joined_at": str(r["joined_at"]) if r["joined_at"] else None,
            "report_count": r["report_count"],
            "last_active": str(r["last_active"]) if r["last_active"] else None,
        }
        for r in rows
    ]


@router.delete("/members/{member_user_id}")
async def remove_member(member_user_id: str, request: Request):
    """Remove a member from the practice. Admin only."""
    practice_id, admin_user_id = await _require_practice_admin(request)

    if member_user_id == admin_user_id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself. Use /practice/leave instead.")

    pool = await _get_pool()
    result = await pool.execute(
        "DELETE FROM practice_members WHERE practice_id = $1::uuid AND user_id = $2::uuid",
        practice_id, member_user_id,
    )
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="Member not found in this practice.")

    _invalidate_practice_cache(member_user_id)
    return {"removed": True}


@router.patch("/members/{member_user_id}/role")
async def update_member_role(member_user_id: str, request: Request):
    """Promote/demote a member. Admin only."""
    practice_id, admin_user_id = await _require_practice_admin(request)

    if member_user_id == admin_user_id:
        raise HTTPException(status_code=400, detail="Cannot change your own role.")

    try:
        body = await request.json()
    except Exception:
        body = {}
    new_role = body.get("role", "").strip()
    if new_role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'member'.")

    pool = await _get_pool()
    result = await pool.execute(
        "UPDATE practice_members SET role = $1 WHERE practice_id = $2::uuid AND user_id = $3::uuid",
        new_role, practice_id, member_user_id,
    )
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="Member not found in this practice.")

    _invalidate_practice_cache(member_user_id)
    return {"user_id": member_user_id, "role": new_role}


# ---------------------------------------------------------------------------
# Practice Settings (admin only)
# ---------------------------------------------------------------------------


@router.patch("/settings")
async def update_practice_settings(request: Request):
    """Update practice name, specialty, sharing_enabled. Admin only."""
    practice_id, _ = await _require_practice_admin(request)

    try:
        body = await request.json()
    except Exception:
        body = {}

    pool = await _get_pool()

    allowed = {"name", "specialty", "sharing_enabled"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update.")

    set_parts = []
    values = []
    idx = 1
    for k, v in updates.items():
        set_parts.append(f"{k} = ${idx}")
        values.append(v)
        idx += 1
    set_parts.append(f"updated_at = NOW()")
    values.append(practice_id)

    await pool.execute(
        f"UPDATE practices SET {', '.join(set_parts)} WHERE id = ${idx}::uuid",
        *values,
    )

    # If sharing was toggled, invalidate all members' cache
    if "sharing_enabled" in updates:
        member_ids = await pool.fetch(
            "SELECT user_id FROM practice_members WHERE practice_id = $1::uuid",
            practice_id,
        )
        for m in member_ids:
            _invalidate_practice_cache(str(m["user_id"]))

    row = await pool.fetchrow("SELECT * FROM practices WHERE id = $1::uuid", practice_id)
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "specialty": row["specialty"],
        "join_code": row["join_code"],
        "sharing_enabled": row["sharing_enabled"],
        "created_at": str(row["created_at"]),
    }


@router.post("/regenerate-code")
async def regenerate_join_code(request: Request):
    """Generate a new join code. Admin only."""
    practice_id, _ = await _require_practice_admin(request)
    pool = await _get_pool()

    for _ in range(10):
        new_code = _generate_join_code()
        conflict = await pool.fetchrow(
            "SELECT id FROM practices WHERE join_code = $1", new_code,
        )
        if not conflict:
            break
    else:
        raise HTTPException(status_code=500, detail="Failed to generate unique join code.")

    await pool.execute(
        "UPDATE practices SET join_code = $1, updated_at = NOW() WHERE id = $2::uuid",
        new_code, practice_id,
    )
    return {"join_code": new_code}


# ---------------------------------------------------------------------------
# Usage Dashboard (admin only)
# ---------------------------------------------------------------------------


@router.get("/usage")
async def practice_usage(request: Request):
    """Aggregated usage across all practice members. Admin only."""
    practice_id, _ = await _require_practice_admin(request)

    since = request.query_params.get("since", "2000-01-01T00:00:00Z")
    pool = await _get_pool()

    row = await pool.fetchrow(
        "SELECT * FROM practice_usage_summary($1::uuid, $2::timestamptz)",
        practice_id, since,
    )
    if not row:
        return {
            "total_members": 0,
            "total_queries": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "deep_analysis_count": 0,
        }

    return {
        "total_members": row["total_members"],
        "total_queries": row["total_queries"],
        "total_input_tokens": row["total_input_tokens"],
        "total_output_tokens": row["total_output_tokens"],
        "deep_analysis_count": row["deep_analysis_count"],
    }
