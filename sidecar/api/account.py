"""Account management endpoints: data export and account deletion.

Web-only (REQUIRE_AUTH) — these endpoints need a valid JWT.
Desktop mode users manage their data via local files.
"""

import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

logger = logging.getLogger(__name__)

REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "").lower() == "true"
_USE_PG = bool(os.getenv("DATABASE_URL", ""))

router = APIRouter(prefix="/account", tags=["account"])


def _get_user_id(request: Request) -> str:
    """Extract user_id from request state. Raises 401 if missing."""
    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return uid


async def _db_call(method_name: str, *args, user_id=None, **kwargs):
    """Call a database method — same bridge pattern as routes.py."""
    from storage import get_active_db
    db = get_active_db()
    method = getattr(db, method_name)
    if _USE_PG:
        return await method(*args, user_id=user_id, **kwargs)
    else:
        return method(*args, **kwargs)


@router.get("/export")
async def export_account_data(request: Request):
    """Export all user data as a JSON file download."""
    if not REQUIRE_AUTH:
        raise HTTPException(status_code=404, detail="Not available in desktop mode.")

    user_id = _get_user_id(request)

    # Collect all user data across tables
    settings = await _db_call("get_all_settings", user_id=user_id) or {}
    history_data = await _db_call("list_history", offset=0, limit=10000, user_id=user_id)
    history_items = history_data[0] if isinstance(history_data, tuple) else history_data
    templates_data = await _db_call("list_templates", user_id=user_id)
    templates_items = templates_data[0] if isinstance(templates_data, tuple) else templates_data
    letters_data = await _db_call("list_letters", offset=0, limit=10000, user_id=user_id)
    letters_items = letters_data[0] if isinstance(letters_data, tuple) else letters_data
    teaching_points = await _db_call("list_teaching_points", user_id=user_id)

    export = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "settings": settings,
        "history": history_items if isinstance(history_items, list) else [],
        "templates": templates_items if isinstance(templates_items, list) else [],
        "letters": letters_items if isinstance(letters_items, list) else [],
        "teaching_points": teaching_points if isinstance(teaching_points, list) else [],
    }

    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "export_account", "account")

    content = json.dumps(export, indent=2, default=str)
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="explify-data-export.json"',
        },
    )


@router.post("/delete")
async def delete_account(request: Request):
    """Permanently delete all user data and the auth account.

    Expects JSON body: {"confirmation": "DELETE"}
    """
    if not REQUIRE_AUTH:
        raise HTTPException(status_code=404, detail="Not available in desktop mode.")

    user_id = _get_user_id(request)

    # Verify confirmation
    try:
        body = await request.json()
    except Exception:
        body = {}
    if body.get("confirmation") != "DELETE":
        raise HTTPException(
            status_code=400,
            detail='Must include {"confirmation": "DELETE"} to confirm account deletion.',
        )

    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "delete_account", "account")

    # Delete data from all tables
    tables_to_clear = [
        "history", "templates", "letters", "teaching_points",
        "settings", "term_preferences", "conditional_rules", "style_profiles",
    ]

    deleted_counts = {}
    for table in tables_to_clear:
        try:
            count = await _delete_all_user_rows(table, user_id)
            deleted_counts[table] = count
        except Exception as e:
            logger.warning("Failed to delete from %s for user %s: %s", table, user_id, e)
            deleted_counts[table] = f"error: {e}"

    # Delete auth user via Cognito Admin API
    auth_deleted = False
    try:
        auth_deleted = await _delete_cognito_user(user_id)
    except Exception as e:
        logger.error("Failed to delete Cognito auth user %s: %s", user_id, e)

    logger.info("Account deleted for user %s: tables=%s, auth=%s", user_id, deleted_counts, auth_deleted)

    return {
        "deleted": True,
        "tables_cleared": deleted_counts,
        "auth_deleted": auth_deleted,
    }


async def _delete_all_user_rows(table: str, user_id: str) -> int:
    """Delete all rows for a user from a given table. Returns count deleted."""
    from storage.pg_database import _get_pool

    # Whitelist tables to prevent SQL injection
    allowed = {
        "history", "templates", "letters", "teaching_points",
        "settings", "term_preferences", "conditional_rules", "style_profiles",
    }
    if table not in allowed:
        return 0

    pool = await _get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            f"DELETE FROM {table} WHERE user_id = $1", user_id
        )
        # asyncpg returns "DELETE N"
        count_str = result.split(" ")[-1] if result else "0"
        return int(count_str)


async def _delete_cognito_user(user_id: str) -> bool:
    """Delete a Cognito user using the AWS SDK (boto3)."""
    user_pool_id = os.getenv("COGNITO_USER_POOL_ID", "")
    region = os.getenv("AWS_REGION", "us-east-1")

    if not user_pool_id:
        logger.warning("Cannot delete auth user: missing COGNITO_USER_POOL_ID")
        return False

    try:
        import boto3
        client = boto3.client("cognito-idp", region_name=region)

        # Cognito admin API requires username, not sub. Look up the user first.
        # The user_id (sub) is what we have from the JWT.
        # Use admin_get_user by filtering users by sub attribute.
        resp = client.list_users(
            UserPoolId=user_pool_id,
            Filter=f'sub = "{user_id}"',
            Limit=1,
        )

        users = resp.get("Users", [])
        if not users:
            logger.warning("No Cognito user found for sub %s", user_id)
            return False

        username = users[0]["Username"]
        client.admin_delete_user(
            UserPoolId=user_pool_id,
            Username=username,
        )
        return True
    except Exception as e:
        logger.error("Cognito user deletion failed for %s: %s", user_id, e)
        return False
