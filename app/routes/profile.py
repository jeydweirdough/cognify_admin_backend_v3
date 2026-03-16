"""
Mobile student profile routes.
  PATCH /api/mobile/student/profile  — update own profile fields
  GET   /api/mobile/student/profile  — fetch own profile
"""
from fastapi import APIRouter, Request
from app.db import fetchone, execute_returning
from app.middleware.auth import mobile_permission_required
from app.utils.responses import ok, error, not_found
from app.utils.validators import clean_str

mobile_profile_router = APIRouter(
    prefix="/api/mobile/student/profile",
    tags=["mobile-profile"],
)

UPDATABLE_FIELDS = {
    "first_name":    ("first_name",    lambda v: clean_str(v)),
    "last_name":     ("last_name",     lambda v: clean_str(v)),
    "username":      ("username",      lambda v: clean_str(v)),
    "daily_goal":    ("daily_goal",    lambda v: clean_str(v)),
    "personal_note": ("personal_note", lambda v: v.strip() if v else None),
    "photo_avatar":  ("photo_avatar",  lambda v: clean_str(v)),
    "avatar_index":  ("avatar_index",  lambda v: int(v) if v is not None else None),
}


def _fmt_profile(u: dict) -> dict:
    u["id"] = str(u["id"])
    u.pop("password", None)
    u["full_name"] = " ".join(filter(None, [u.get("first_name"), u.get("last_name")]))
    if u.get("date_created"):
        u["date_created"] = u["date_created"].isoformat()
    if u.get("last_login"):
        u["last_login"] = u["last_login"].isoformat()
    return u


@mobile_profile_router.get("")
async def get_profile(request: Request):
    auth = mobile_permission_required("mobile_view_profile")(request)
    user = fetchone(
        """SELECT id, cvsu_id, first_name, last_name, email,
                  username, daily_goal, personal_note, photo_avatar, avatar_index,
                  status, date_created, last_login
           FROM users WHERE id = %s""",
        [auth.user_id],
    )
    if not user:
        return not_found("User not found")
    return ok(_fmt_profile(user))


@mobile_profile_router.patch("")
async def update_profile(request: Request):
    auth = mobile_permission_required("mobile_edit_profile")(request)
    try:
        body = await request.json()
    except Exception:
        return error("Invalid JSON body")

    if not isinstance(body, dict) or not body:
        return error("Nothing to update")

    set_clauses = []
    params = []

    for field, (col, transform) in UPDATABLE_FIELDS.items():
        if field in body:
            value = body[field]
            set_clauses.append(f"{col} = %s")
            params.append(transform(value) if value is not None else None)

    if not set_clauses:
        return error("No valid fields to update")

    params.append(auth.user_id)
    updated = execute_returning(
        f"""UPDATE users
            SET {', '.join(set_clauses)}
            WHERE id = %s
            RETURNING id, cvsu_id, first_name, last_name, email,
                      username, daily_goal, personal_note, photo_avatar, avatar_index,
                      status, date_created, last_login""",
        params,
    )
    if not updated:
        return not_found("User not found")
    return ok(_fmt_profile(updated))
