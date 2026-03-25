"""
Supabase Storage utility.

Design decisions for production (free-tier friendly):
  - PDFs  : single "pdfs" bucket, organised into sub-folders by subject slug.
            Path pattern:  pdfs/{subject-slug}/{uuid}.pdf
            No per-subject buckets — Supabase free tier allows very few buckets.
  - Avatars: stored as a base64 data URI directly in the users.photo_avatar DB
            column. No bucket is used for avatars at all. This keeps the free
            tier storage quota free for actual content (PDFs).
  - Preset avatars: served from backend static files, not Supabase storage.
"""

import os
import uuid
import base64
import re

import httpx

# ── Constants ──────────────────────────────────────────────────────────────────

PDF_BUCKET = "pdfs"

# ── Internal helpers ───────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    """Convert a subject name to a safe folder segment (lowercase, hyphens only)."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return cleaned or "default"


def _supabase_creds() -> tuple[str, str]:
    """Return (supabase_url, service_role_key). Raises if missing."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.")
    return url.rstrip("/"), key


def _storage_headers(key: str) -> dict:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }


def _ensure_bucket_exists(client: httpx.Client, url: str, key: str, bucket: str) -> None:
    """Create the bucket if it doesn't already exist (idempotent)."""
    headers = _storage_headers(key)
    resp = client.get(f"{url}/storage/v1/bucket/{bucket}", headers=headers)
    bucket_missing = resp.status_code == 404 or (
        resp.status_code == 400 and "not found" in resp.text.lower()
    )
    if bucket_missing:
        create = client.post(
            f"{url}/storage/v1/bucket",
            headers=headers,
            json={"id": bucket, "name": bucket, "public": True},
        )
        create.raise_for_status()


def _strip_data_uri(data_str: str) -> tuple[str, str]:
    """Strip the data URI prefix and return (raw_base64, mime_type)."""
    mime = "application/octet-stream"
    if data_str.startswith("data:"):
        header, data_str = data_str.split(",", 1)
        match = re.search(r"data:(.*?);", header)
        if match:
            mime = match.group(1)
    return data_str, mime


# ── PDF upload ─────────────────────────────────────────────────────────────────

def upload_pdf_base64(base64_str: str, filename: str, subject_name: str) -> str:
    """
    Upload a base64-encoded PDF to the shared "pdfs" Supabase bucket.

    Storage layout (no root-level clutter):
        pdfs/{subject-slug}/{uuid}.pdf

    Returns the public URL of the uploaded file.
    """
    supabase_url, supabase_key = _supabase_creds()

    base64_str, _ = _strip_data_uri(base64_str)

    try:
        file_bytes = base64.b64decode(base64_str)
    except Exception as exc:
        raise ValueError(f"Invalid Base64 string: {exc}") from exc

    subject_slug = _slugify(subject_name)
    object_path = f"{subject_slug}/{uuid.uuid4().hex}.pdf"
    upload_url = f"{supabase_url}/storage/v1/object/{PDF_BUCKET}/{object_path}"

    headers = {
        **_storage_headers(supabase_key),
        "Content-Type": "application/pdf",
    }

    with httpx.Client(timeout=60) as client:
        _ensure_bucket_exists(client, supabase_url, supabase_key, PDF_BUCKET)
        resp = client.post(upload_url, headers=headers, content=file_bytes)
        if resp.status_code >= 400:
            raise RuntimeError(f"Supabase storage error ({resp.status_code}): {resp.text}")

    return f"{supabase_url}/storage/v1/object/public/{PDF_BUCKET}/{object_path}"


def delete_pdf_by_url(public_url: str) -> None:
    """
    Delete a previously uploaded PDF from the "pdfs" bucket given its public URL.
    Fails silently if the object no longer exists (idempotent).
    """
    try:
        supabase_url, supabase_key = _supabase_creds()
    except ValueError:
        return

    prefix = f"{supabase_url}/storage/v1/object/public/{PDF_BUCKET}/"
    if not public_url.startswith(prefix):
        return  # Not a file we own — skip

    object_path = public_url[len(prefix):]
    delete_url = f"{supabase_url}/storage/v1/object/{PDF_BUCKET}/{object_path}"

    with httpx.Client(timeout=30) as client:
        client.delete(delete_url, headers=_storage_headers(supabase_key))


# ── Avatar helpers (DB-stored, no Supabase bucket needed) ─────────────────────

def validate_and_normalise_avatar(value: str) -> str:
    """
    Validate and return an avatar value for storage in the DB.

    Accepts:
      • A base64 data URI  (data:image/...;base64,...)  → stored directly in DB
      • A plain URL string (preset or external)         → stored as-is

    Raises ValueError if the data URI is malformed or the decoded image > 2 MB.
    """
    if not value:
        return value

    if value.startswith("data:image"):
        raw, _ = _strip_data_uri(value)
        try:
            decoded = base64.b64decode(raw)
        except Exception as exc:
            raise ValueError(f"Invalid base64 image: {exc}") from exc

        max_bytes = 2 * 1024 * 1024  # 2 MB
        if len(decoded) > max_bytes:
            raise ValueError(
                f"Avatar image too large ({len(decoded) // 1024} KB). Maximum allowed is 2 MB."
            )

    return value
