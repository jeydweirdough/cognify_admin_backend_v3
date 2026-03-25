"""
Supabase Storage utility.

Architecture:
  - PDFs    : Stored in dynamically created buckets named after the subject slug.
              Path pattern:  {subject_slug}/{filename}.pdf
  - Avatars : single "avatars" bucket. Only phone-uploaded photos go here.
              Path pattern:  avatars/{user_id}-{first_name_slug}.png
"""

import os
import uuid
import base64
import re
import httpx

# ── Constants & Exceptions ─────────────────────────────────────────────────────

AVATAR_BUCKET = "avatars"

class DuplicateFileError(Exception):
    """Raised when a file with the same name already exists in the bucket."""
    pass

# ── Internal helpers ───────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    """Convert a subject name to a safe bucket/folder segment (lowercase, hyphens only)."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return cleaned or "default-subject"


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
    
    bucket_url = f"{url}/storage/v1/bucket/{bucket}"
    resp = client.get(bucket_url, headers=headers)
    
    if resp.status_code != 200:
        print(f"\n[Supabase Storage INFO] Checking bucket '{bucket}' returned {resp.status_code}: {resp.text}")
    
    bucket_missing = resp.status_code == 404 or (
        resp.status_code == 400 and "not found" in resp.text.lower()
    )
    
    if bucket_missing:
        print(f"[Supabase Storage INFO] Bucket '{bucket}' missing. Attempting to auto-create...")
        
        create_resp = client.post(
            f"{url}/storage/v1/bucket",
            headers=headers,
            json={"id": bucket, "name": bucket, "public": True},
        )
        
        if create_resp.status_code >= 400 and "already exists" not in create_resp.text.lower():
            print(f"[Supabase Storage ERROR] Failed to auto-create bucket '{bucket}'.")
            print(f"Status: {create_resp.status_code}")
            print(f"Response: {create_resp.text}\n")
            create_resp.raise_for_status()
        else:
            print(f"[Supabase Storage SUCCESS] Auto-created bucket '{bucket}' successfully.\n")


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

def upload_pdf_bytes(file_bytes: bytes, filename: str, bucket_name: str) -> str:
    """
    Upload raw PDF bytes to a dynamically created subject bucket.
    """
    if not bucket_name:
        bucket_name = "default-subject"
        
    supabase_url, supabase_key = _supabase_creds()
    object_path = filename
    upload_url = f"{supabase_url}/storage/v1/object/{bucket_name}/{object_path}"

    headers = {
        **_storage_headers(supabase_key),
        "Content-Type": "application/pdf",
        "x-upsert": "false",  # strict: do not overwrite if file already exists
    }

    with httpx.Client(timeout=60) as client:
        _ensure_bucket_exists(client, supabase_url, supabase_key, bucket_name)
        resp = client.post(upload_url, headers=headers, content=file_bytes)
        
        # --- Handle specific Duplicate file error (409) ---
        if resp.status_code == 400 and "Duplicate" in resp.text:
            raise DuplicateFileError(f"A file named '{filename}' already exists in the '{bucket_name}' subject.")
            
        if resp.status_code >= 400:
            print(f"\n[Supabase Storage ERROR] Failed to upload '{object_path}' to bucket '{bucket_name}'")
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text}\n")
            raise RuntimeError(f"Supabase storage error ({resp.status_code}): {resp.text}")

    return f"{supabase_url}/storage/v1/object/public/{bucket_name}/{object_path}"


def upload_pdf_base64(base64_str: str, filename: str, subject_name: str) -> str:
    """
    Upload a base64-encoded PDF to the dynamically created subject bucket.
    """
    supabase_url, supabase_key = _supabase_creds()
    base64_str, _ = _strip_data_uri(base64_str)

    try:
        file_bytes = base64.b64decode(base64_str)
    except Exception as exc:
        raise ValueError(f"Invalid Base64 string: {exc}") from exc

    bucket_name = _slugify(subject_name)
    object_path = f"{uuid.uuid4().hex}.pdf"
    upload_url = f"{supabase_url}/storage/v1/object/{bucket_name}/{object_path}"

    headers = {
        **_storage_headers(supabase_key),
        "Content-Type": "application/pdf",
        "x-upsert": "false",
    }

    with httpx.Client(timeout=60) as client:
        _ensure_bucket_exists(client, supabase_url, supabase_key, bucket_name)
        resp = client.post(upload_url, headers=headers, content=file_bytes)
        
        if resp.status_code >= 400:
            print(f"\n[Supabase Storage ERROR] Failed to upload '{object_path}' to bucket '{bucket_name}'")
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text}\n")
            raise RuntimeError(f"Supabase storage error ({resp.status_code}): {resp.text}")

    return f"{supabase_url}/storage/v1/object/public/{bucket_name}/{object_path}"


def delete_pdf_by_url(public_url: str) -> None:
    """
    Delete a previously uploaded PDF from its dynamic subject bucket given its public URL.
    """
    if not public_url:
        return

    try:
        supabase_url, supabase_key = _supabase_creds()
    except ValueError:
        return

    # Check if the URL belongs to our Supabase storage
    prefix = f"{supabase_url}/storage/v1/object/public/"
    if not public_url.startswith(prefix):
        return  # Not a file we own — skip

    remainder = public_url[len(prefix):]
    parts = remainder.split("/", 1)
    
    # Needs to at least contain a bucket and a file path
    if len(parts) != 2:
        return
        
    bucket_name, object_path = parts
    delete_url = f"{supabase_url}/storage/v1/object/{bucket_name}/{object_path}"

    with httpx.Client(timeout=30) as client:
        resp = client.delete(delete_url, headers=_storage_headers(supabase_key))
        # Ignore 404s (the file is already deleted or doesn't exist)
        if resp.status_code >= 400 and resp.status_code != 404:
            print(f"[Warning] Failed to delete PDF {object_path} from bucket {bucket_name}: {resp.text}")


# ── Avatar upload / helpers ──────────────────────────────────────────────────────────────

def upload_avatar_bytes(image_bytes: bytes, user_id: str, first_name: str, mime_type: str = "image/png") -> str:
    supabase_url, supabase_key = _supabase_creds()
    first_slug = _slugify(first_name) if first_name else "user"
    filename = f"{user_id}-{first_slug}.png"
    upload_url = f"{supabase_url}/storage/v1/object/{AVATAR_BUCKET}/{filename}"
    headers = {
        **_storage_headers(supabase_key),
        "Content-Type": mime_type,
        "x-upsert": "true",
    }
    with httpx.Client(timeout=60) as client:
        _ensure_bucket_exists(client, supabase_url, supabase_key, AVATAR_BUCKET)
        resp = client.post(upload_url, headers=headers, content=image_bytes)
        if resp.status_code >= 400:
            raise RuntimeError(f"Supabase storage error ({resp.status_code}): {resp.text}")
    return f"{supabase_url}/storage/v1/object/public/{AVATAR_BUCKET}/{filename}"

def validate_and_normalise_avatar(value: str) -> str:
    if not value: return value
    if value.startswith("data:image"):
        raw, _ = _strip_data_uri(value)
        try:
            decoded = base64.b64decode(raw)
        except Exception as exc:
            raise ValueError(f"Invalid base64 image: {exc}") from exc
        max_bytes = 2 * 1024 * 1024
        if len(decoded) > max_bytes:
            raise ValueError(f"Avatar image too large ({len(decoded) // 1024} KB). Maximum allowed is 2 MB.")
    return value