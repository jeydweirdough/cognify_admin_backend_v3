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
from app.utils.storage import validate_and_normalise_avatar, upload_avatar_bytes

mobile_profile_router = APIRouter(
    prefix="/api/mobile/student/profile",
    tags=["mobile-profile"],
)

UPDATABLE_FIELDS = {
    "first_name":           ("first_name",           lambda v: clean_str(v)),
    "last_name":            ("last_name",            lambda v: clean_str(v)),
    "username":             ("username",             lambda v: clean_str(v)),
    "daily_goal":           ("daily_goal",           lambda v: clean_str(v)),
    "personal_note":        ("personal_note",        lambda v: v.strip() if v else None),
    "photo_avatar":         ("photo_avatar",         lambda v: clean_str(v)),
    "has_taken_diagnostic": ("has_taken_diagnostic", lambda v: bool(v)),
    "readiness_score":      ("readiness_score",      lambda v: float(v) if v is not None else None),
}

def get_preset_url(index: int) -> str | None:
    """
    Return the preset avatar identifier stored in the DB.
    We store a simple token like "preset:a" rather than a Supabase URL so the
    frontend/mobile app can resolve it to a local bundled asset, and we don't
    consume any Supabase storage quota for static images.
    """
    if index < 0 or index > 7:
        return None
    letters = ["a", "b", "c", "d", "e", "f", "g", "h"]
    return f"preset:{letters[index]}"


def _fmt_profile(u: dict) -> dict:
    u["id"] = str(u["id"])
    u.pop("password", None)
    u["full_name"] = " ".join(filter(None, [u.get("first_name"), u.get("last_name")]))
    if u.get("date_created"):
        u["date_created"] = u["date_created"].isoformat()
    if u.get("last_login"):
        u["last_login"] = u["last_login"].isoformat()
    u["hasTakenDiagnostic"] = bool(u.pop("has_taken_diagnostic", False))
    u["readinessScore"] = float(u.pop("readiness_score", 0) or 0)
    return u


@mobile_profile_router.get("")
async def get_profile(request: Request):
    auth = mobile_permission_required("mobile_view_profile")(request)
    user = fetchone(
        """SELECT id, cvsu_id, first_name, last_name, email,
                  username, daily_goal, personal_note, photo_avatar,
                  status, date_created, last_login,
                  has_taken_diagnostic, readiness_score
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
    except Exception as e:
        print(f"[PROFILE] JSON parse error: {e}")
        return error("Invalid JSON body")

    if not isinstance(body, dict) or not body:
        print(f"[PROFILE] Empty body: {body}")
        return error("Nothing to update")

    # Debug: log what fields are being received
    photo_val = body.get("photo_avatar")

    # Pre-process fields to handle logic between them
    # If a preset avatar is chosen, it overrides the photo_avatar with the preset URL
    if "avatar_index" in body:
        idx = body["avatar_index"]
        if idx is not None:
            try:
                idx = int(idx)
                if idx >= 0:
                    preset_url = get_preset_url(idx)
                    if preset_url:
                        body["photo_avatar"] = preset_url
                elif idx == -1:
                    # If explicitly setting to -1 but no photo_avatar is provided, 
                    # we keep whatever photo_avatar was sent or existing.
                    pass
            except (ValueError, TypeError):
                return error("Invalid avatar_index")

    set_clauses = []
    params = []

    for field, (col, transform) in UPDATABLE_FIELDS.items():
        if field in body:
            value = body[field]
            
            # Avatar: if it's a base64 data URI from the phone camera/gallery,
            # upload it to Supabase Storage and store only the public URL in DB.
            # Preset tokens (e.g. "preset:a") are stored as-is — no bucket needed.
            if field == "photo_avatar" and isinstance(value, str) and value.startswith("data:image"):
                try:
                    validate_and_normalise_avatar(value)  # size/format check
                    # Decode base64 and upload
                    import base64 as _b64, re as _re
                    mime_match = _re.search(r"data:(image/[^;]+);base64,", value)
                    mime_type  = mime_match.group(1) if mime_match else "image/png"
                    raw_b64    = value.split(",", 1)[1]
                    img_bytes  = _b64.b64decode(raw_b64)
                    # Fetch first_name from DB for the filename
                    user_row   = fetchone("SELECT first_name FROM users WHERE id = %s", [auth.user_id])
                    first_name = (user_row or {}).get("first_name", "user")
                    value = upload_avatar_bytes(img_bytes, str(auth.user_id), first_name, mime_type)
                except Exception as e:
                    return error(f"Invalid profile photo: {str(e)}")
            
            set_clauses.append(f"{col} = %s")
            params.append(transform(value) if value is not None else None)

    if not set_clauses:
        return error("No valid fields to update")

    params.append(auth.user_id)
    sql = f"""UPDATE users
            SET {', '.join(set_clauses)}
            WHERE id = %s
            RETURNING id, cvsu_id, first_name, last_name, email,
                      username, daily_goal, personal_note, photo_avatar,
                      status, date_created, last_login,
                      has_taken_diagnostic, readiness_score"""
    try:
        updated = execute_returning(sql, params)
        if not updated:
            return not_found("User not found")
        return ok(_fmt_profile(updated))
    except Exception as e:
        print(f"[PROFILE] Database update error: {e}")
        return error("Failed to update profile in database")