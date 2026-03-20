import os
import uuid
import base64
import httpx
import re
from typing import Optional

def _slugify_bucket_name(name: str) -> str:
    """Converts a subject name to a valid Supabase bucket name (lowercase alphanumeric & hyphens)."""
    cleaned = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if not cleaned:
        return "default-subject"
    return f"subject-{cleaned}"

def _ensure_bucket_exists(client: httpx.Client, supabase_url: str, supabase_key: str, bucket: str):
    """Checks if the bucket exists. If not, creates it as a public bucket."""
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
    }
    
    url = f"{supabase_url.rstrip('/')}/storage/v1/bucket/{bucket}"
    rep = client.get(url, headers=headers)
    
    # Supabase sometimes returns 400 with 'Bucket not found' JSON natively instead of 404
    if rep.status_code == 404 or (rep.status_code == 400 and "Bucket not found" in rep.text):
        # Bucket doesn't exist, create it!
        create_url = f"{supabase_url.rstrip('/')}/storage/v1/bucket"
        payload = {
            "id": bucket,
            "name": bucket,
            "public": True
        }
        create_rep = client.post(create_url, headers=headers, json=payload)
        create_rep.raise_for_status()

def upload_pdf_base64(base64_str: str, filename: str, subject_name: str) -> Optional[str]:
    """
    Decodes a Base64 string and uploads it to a dynamically created Supabase Storage bucket.
    Returns the public URL of the uploaded file.
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_KEY"))
    
    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for file uploads.")

    bucket = _slugify_bucket_name(subject_name)

    # Remove data URI scheme
    if base64_str.startswith("data:"):
        parts = base64_str.split(",", 1)
        if len(parts) > 1:
            base64_str = parts[1]

    try:
        file_bytes = base64.b64decode(base64_str)
    except Exception as e:
        raise ValueError(f"Invalid Base64 string: {e}")

    ext = os.path.splitext(filename)[1]
    if not ext:
        ext = ".pdf"
    unique_filename = f"{uuid.uuid4().hex}{ext}"

    url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{unique_filename}"
    
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/pdf"
    }

    with httpx.Client(timeout=30) as client:
        # 1. Auto-create the bucket if it doesn't exist
        _ensure_bucket_exists(client, supabase_url, supabase_key, bucket)
        
        # 2. Upload the file
        resp = client.post(url, headers=headers, content=file_bytes)
        if resp.status_code >= 400:
            raise RuntimeError(f"Storage error ({resp.status_code}): {resp.text}")

    # Return the authenticated public URL
    return f"{supabase_url.rstrip('/')}/storage/v1/object/public/{bucket}/{unique_filename}"
