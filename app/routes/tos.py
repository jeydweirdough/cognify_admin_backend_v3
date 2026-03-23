"""
tos.py — TOS Versions management routes.

  POST /api/web/admin/tos/upload   → upload PDF, run extractor, save DRAFT
  GET  /api/web/admin/tos          → list (no data blob)
  GET  /api/web/admin/tos/:id      → single version (full data)
  PUT  /api/web/admin/tos/:id      → update label/year/notes/status/data
  POST /api/web/admin/tos/:id/activate
  DELETE /api/web/admin/tos/:id

  GET /api/mobile/tos/active       → read-only active TOS for students

The TOS data structure (tos_versions.data) mirrors extractor.py output:
  {
    "subjects": [
      {
        "annex": "A", "board": "Psychologist",
        "subject": "...", "weight": "20%",
        "sections": [
          {
            "title": "...",
            "competencies": [
              {
                "code": "1.1", "description": "...",
                "weight": "5%", "no_of_items": 4,
                "bloom_remembering": 1, "bloom_understanding": 1,
                "bloom_applying": 1, "bloom_analyzing": 1,
                "bloom_evaluating": 0, "bloom_creating": 0
              }
            ],
            "total": { ... }
          }
        ],
        "grand_total": { ... }
      }
    ]
  }
"""

import hashlib
import os
import tempfile
from datetime import datetime, timezone

from fastapi import APIRouter, Path, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from psycopg2.extras import Json as PgJson

from app.db import fetchone, fetchall, execute, execute_returning, paginate
from app.middleware.auth import login_required, permission_required
from app.utils.responses import ok, created, no_content, error, not_found
from app.utils.pagination import get_page_params, get_search
from app.utils.validators import clean_str
from app.utils.log import log_action

admin_tos_router  = APIRouter(prefix="/api/web/admin/tos",    tags=["tos"])
faculty_tos_router = APIRouter(prefix="/api/web/faculty/tos", tags=["tos-faculty"])
mobile_tos_router = APIRouter(prefix="/api/mobile/tos",      tags=["tos-mobile"])

# ── Extractor module (lives at app/extractor/extractor.py) ────────────────────
from app.extractor import extractor as _ext


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _serialize(row: dict) -> dict:
    """Normalize a tos_versions row for JSON output."""
    row["id"] = str(row["id"])
    if row.get("created_by"):
        row["created_by"] = str(row["created_by"])
    for ts_col in ("created_at", "updated_at", "extracted_at"):
        if row.get(ts_col) and hasattr(row[ts_col], "isoformat"):
            row[ts_col] = row[ts_col].isoformat()
    if row.get("data") is None:
        row["data"] = {}
    return row


def _sha256_of_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _deactivate_current_active():
    """Archive the currently ACTIVE version (if any) before activating a new one."""
    execute(
        "UPDATE tos_versions SET status = 'ARCHIVED', updated_at = NOW() WHERE status = 'ACTIVE'"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — UPLOAD PDF → extract → save as DRAFT
# ─────────────────────────────────────────────────────────────────────────────

@admin_tos_router.post("/upload")
async def upload_tos_pdf(
    request: Request,
    file: UploadFile = File(...),
    label: str = Form(""),
    academic_year: str = Form("2024-2025"),
    notes: str = Form(""),
):
    """
    Accept a TOS PDF, run it through the pdf_extractor module, and persist
    the result as a new DRAFT tos_versions row.

    multipart/form-data fields:
      file          — the PDF file (required)
      label         — human-readable version name (defaults to filename stem)
      academic_year — e.g. "2024-2025"
      notes         — optional admin notes
    """
    auth = permission_required("create_tos")(request)

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return error("Only PDF files are accepted.", 400)

    pdf_bytes = await file.read()
    if not pdf_bytes:
        return error("Uploaded file is empty.", 400)
    
    source_hash = _sha256_of_bytes(pdf_bytes)

    # Check for duplicate hash — block re-uploading the exact same PDF bytes.
    # Only reject if a non-ARCHIVED version with this hash already exists;
    # allow re-upload if the previous record was archived or deleted.
    existing = fetchone(
        "SELECT id, label, status FROM tos_versions WHERE source_hash = %s AND status != 'ARCHIVED' LIMIT 1",
        [source_hash]
    )
    if existing:
        return error(
            f"This PDF has already been uploaded as \"{existing['label']}\" "
            f"(status: {existing['status'].title()}). "
            "Upload a different PDF to create a new version.",
            409
        )

    version_label = clean_str(label) or Path(file.filename).stem
    version_year  = clean_str(academic_year) or "2024-2025"
    version_notes = clean_str(notes) or None

    # Persistent storage for the PDF
    storage_dir = os.path.join("storage", "tos_pdfs")
    os.makedirs(storage_dir, exist_ok=True)
    pdf_path = os.path.join(storage_dir, f"{source_hash}.pdf")
    
    # Save the PDF if it doesn't exist
    if not os.path.exists(pdf_path):
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)

    # Write PDF to a temp file for the extractor
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        success, status_msg, raw = _ext.extract(tmp_path, source_hash)

        if not success:
            return error(f"Extraction failed: {status_msg}", 422)

        extraction_method = raw.get("extraction_method", "geometry")
        extracted_at_str  = raw.get("extracted_at")
        data_payload      = raw.get("data", {})

        extracted_at = None
        if extracted_at_str:
            try:
                extracted_at = datetime.fromisoformat(
                    extracted_at_str.replace("Z", "+00:00")
                )
            except ValueError:
                extracted_at = datetime.now(timezone.utc)

    except ImportError as exc:
        return error(
            f"pdf_extractor module not found. "
            f"Make sure app/extractor/extractor.py exists. ({exc})",
            500
        )
    except Exception as exc:
        return error(f"Extraction error: {exc}", 500)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    row = execute_returning("""
        INSERT INTO tos_versions (
            label, academic_year, source_hash, extraction_method,
            extracted_at, data, status, notes, created_by
        ) VALUES (%s, %s, %s, %s, %s, %s, 'DRAFT', %s, %s)
        RETURNING *
    """, [
        version_label, version_year, source_hash, extraction_method,
        extracted_at, PgJson(data_payload), version_notes, auth.user_id
    ])

    # Populate pdf_url now that we have the ID
    pdf_url = f"/api/web/admin/tos/{row['id']}/pdf"
    execute("UPDATE tos_versions SET pdf_url = %s WHERE id = %s", [pdf_url, row['id']])
    row["pdf_url"] = pdf_url

    log_action(
        "Uploaded TOS PDF", version_label, row["id"],
        user_id=auth.user_id, ip=auth.ip
    )
    return created(_serialize(row))


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — LIST
# ─────────────────────────────────────────────────────────────────────────────

@admin_tos_router.get("")
async def list_tos_versions(request: Request):
    auth = permission_required("view_tos")(request)

    page, per_page = get_page_params(request)
    search = get_search(request)

    sql = """
        SELECT
            t.id, t.label, t.academic_year, t.source_hash, t.pdf_url,
            t.extraction_method, t.extracted_at,
            t.status, t.notes, t.created_by, t.created_at, t.updated_at,
            u.first_name || ' ' || u.last_name AS created_by_name
        FROM tos_versions t
        LEFT JOIN users u ON u.id = t.created_by
        WHERE 1=1
    """
    params = []

    if search:
        sql += " AND (LOWER(t.label) LIKE LOWER(%s) OR LOWER(t.academic_year) LIKE LOWER(%s))"
        params.extend([f"%{search}%", f"%{search}%"])

    status_filter = request.query_params.get("status")
    if status_filter:
        sql += " AND t.status = %s"
        params.append(status_filter.upper())

    sql += " ORDER BY t.created_at DESC"
    result = paginate(sql, params, page, per_page)

    for row in result["items"]:
        _serialize(row)
        row.pop("data", None)   # exclude heavy blob from list view

    return ok(result)


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — GET ONE (includes full data payload)
# ─────────────────────────────────────────────────────────────────────────────

@admin_tos_router.get("/{tos_id}")
async def get_tos_version(tos_id: str, request: Request):
    auth = permission_required("view_tos")(request)

    row = fetchone("""
        SELECT
            t.*,
            u.first_name || ' ' || u.last_name AS created_by_name
        FROM tos_versions t
        LEFT JOIN users u ON u.id = t.created_by
        WHERE t.id = %s
    """, [tos_id])

    if not row:
        return not_found("TOS version not found")

    return ok(_serialize(row))


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — VIEW PDF
# ─────────────────────────────────────────────────────────────────────────────

@admin_tos_router.get("/{tos_id}/pdf")
async def get_tos_pdf(tos_id: str, request: Request):
    """Serve the original PDF associated with a TOS version."""
    auth = permission_required("view_tos")(request)

    row = fetchone("SELECT source_hash FROM tos_versions WHERE id = %s", [tos_id])
    if not row or not row.get("source_hash"):
        return not_found("TOS version or PDF hash not found")

    source_hash = row["source_hash"]
    pdf_path = os.path.join("storage", "tos_pdfs", f"{source_hash}.pdf")

    if not os.path.exists(pdf_path):
        return not_found("PDF file not found on server. It may have been uploaded before PDF storage was enabled.")

    return FileResponse(
        pdf_path, 
        media_type="application/pdf"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — UPDATE  (label / year / notes / status / data — no PDF re-upload)
# ─────────────────────────────────────────────────────────────────────────────

@admin_tos_router.put("/{tos_id}")
async def update_tos_version(tos_id: str, request: Request):
    auth = permission_required("edit_tos")(request)

    existing = fetchone("SELECT * FROM tos_versions WHERE id = %s", [tos_id])
    if not existing:
        return not_found("TOS version not found")

    try:
        body = await request.json()
    except Exception:
        return error("Invalid JSON body", 400)

    label         = clean_str(body.get("label",         existing["label"]))         or existing["label"]
    academic_year = clean_str(body.get("academic_year", existing["academic_year"])) or existing["academic_year"]
    notes         = clean_str(body.get("notes",         existing.get("notes")))
    status        = (body.get("status") or existing["status"]).upper()
    data          = body.get("data", existing["data"])

    if status not in ("DRAFT", "ACTIVE", "ARCHIVED"):
        return error("status must be DRAFT, ACTIVE, or ARCHIVED", 400)

    if status == "ACTIVE" and existing["status"] != "ACTIVE":
        _deactivate_current_active()

    row = execute_returning("""
        UPDATE tos_versions SET
            label         = %s,
            academic_year = %s,
            notes         = %s,
            status        = %s,
            data          = %s,
            updated_at    = NOW()
        WHERE id = %s
        RETURNING *
    """, [label, academic_year, notes, status, PgJson(data), tos_id])

    log_action("Updated TOS version", label, tos_id, user_id=auth.user_id, ip=auth.ip)
    return ok(_serialize(row))


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — ACTIVATE
# ─────────────────────────────────────────────────────────────────────────────

@admin_tos_router.post("/{tos_id}/activate")
async def activate_tos_version(tos_id: str, request: Request):
    auth = permission_required("edit_tos")(request)

    existing = fetchone("SELECT * FROM tos_versions WHERE id = %s", [tos_id])
    if not existing:
        return not_found("TOS version not found")

    _deactivate_current_active()

    row = execute_returning(
        "UPDATE tos_versions SET status = 'ACTIVE', updated_at = NOW() WHERE id = %s RETURNING *",
        [tos_id]
    )

    log_action("Activated TOS version", existing["label"], tos_id, user_id=auth.user_id, ip=auth.ip)
    return ok(_serialize(row))


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — GET ASSOCIATED SUBJECTS
# ─────────────────────────────────────────────────────────────────────────────

@admin_tos_router.get("/{tos_id}/associated-subjects")
async def get_tos_associated_subjects(tos_id: str, request: Request):
    auth = permission_required("view_tos")(request)

    tos = fetchone("SELECT data FROM tos_versions WHERE id = %s", [tos_id])
    if not tos: return not_found("TOS version not found")

    names = [s.get("subject", "").strip() for s in tos.get("data", {}).get("subjects", []) if s.get("subject")]
    
    if not names:
        return ok([])

    placeholders = ",".join(["%s"] * len(names))
    subjects = fetchall(f"""
        SELECT 
            s.id, s.name, s.status,
            (SELECT COUNT(*) FROM modules WHERE subject_id = s.id) as module_count,
            (SELECT COUNT(*) FROM assessments WHERE subject_id = s.id) as assessment_count
        FROM subjects s
        WHERE LOWER(s.name) IN ({",".join(["LOWER(%s)"] * len(names))})
    """, names)

    for s in subjects:
        s["id"] = str(s["id"])

    return ok(subjects)

# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — GET SUBJECT STATUS
# ─────────────────────────────────────────────────────────────────────────────

@admin_tos_router.get("/{tos_id}/subject-status")
async def get_tos_subject_status(tos_id: str, request: Request):
    auth = permission_required("view_tos")(request)

    tos = fetchone("SELECT data FROM tos_versions WHERE id = %s", [tos_id])
    if not tos: return not_found("TOS version not found")

    names = [s.get("subject", "").strip() for s in tos.get("data", {}).get("subjects", []) if s.get("subject")]
    
    status_map = {n: "MISSING" for n in names}
    
    if names:
        subjects = fetchall(f"SELECT name FROM subjects WHERE LOWER(name) IN ({','.join(['LOWER(%s)'] * len(names))})", names)
        existing = {s["name"].lower() for s in subjects}
        for n in names:
            if n.lower() in existing:
                status_map[n] = "EXISTS"
                
    return ok(status_map)

# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — DELETE WITH OPTIONS
# ─────────────────────────────────────────────────────────────────────────────

@admin_tos_router.post("/{tos_id}/delete-with-options")
async def delete_tos_with_options(tos_id: str, request: Request):
    auth = permission_required("delete_tos")(request)

    existing = fetchone("SELECT * FROM tos_versions WHERE id = %s", [tos_id])
    if not existing:
        return not_found("TOS version not found")

    if existing["status"] == "ACTIVE":
        return error("Cannot delete the currently ACTIVE TOS version. Archive or activate another version first.", 409)
        
    try: body = await request.json()
    except Exception: body = {}
    
    retain_subject_ids = body.get("retain_subject_ids", [])
    
    names = [s.get("subject", "").strip() for s in existing.get("data", {}).get("subjects", []) if s.get("subject")]
    
    if names:
        db_subjects = fetchall(f"SELECT id, name FROM subjects WHERE LOWER(name) IN ({','.join(['LOWER(%s)'] * len(names))})", names)
        for s in db_subjects:
            s_id_str = str(s["id"])
            if s_id_str not in retain_subject_ids:
                execute("DELETE FROM subjects WHERE id = %s", [s_id_str])
                log_action("Deleted subject during TOS removal", s["name"], s_id_str, user_id=auth.user_id, ip=auth.ip)

    execute("DELETE FROM tos_versions WHERE id = %s", [tos_id])
    log_action("Deleted TOS version (with options)", existing["label"], tos_id, user_id=auth.user_id, ip=auth.ip)
    
    return no_content()


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — DELETE
# ─────────────────────────────────────────────────────────────────────────────

@admin_tos_router.delete("/{tos_id}")
async def delete_tos_version(tos_id: str, request: Request):
    auth = permission_required("delete_tos")(request)

    existing = fetchone("SELECT * FROM tos_versions WHERE id = %s", [tos_id])
    if not existing:
        return not_found("TOS version not found")

    if existing["status"] == "ACTIVE":
        return error(
            "Cannot delete the currently ACTIVE TOS version. "
            "Archive or activate another version first.",
            409
        )

    execute("DELETE FROM tos_versions WHERE id = %s", [tos_id])
    log_action("Deleted TOS version", existing["label"], tos_id, user_id=auth.user_id, ip=auth.ip)
    return no_content()


# ─────────────────────────────────────────────────────────────────────────────
# FACULTY — GET ACTIVE TOS  (read-only, faculty members)
# ─────────────────────────────────────────────────────────────────────────────

@faculty_tos_router.get("/active")
async def get_active_tos_faculty(request: Request):
    auth = permission_required("view_tos")(request)

    row = fetchone("""
        SELECT id, label, academic_year, data, extracted_at, updated_at
        FROM tos_versions
        WHERE status = 'ACTIVE'
        ORDER BY updated_at DESC
        LIMIT 1
    """)

    if not row:
        return not_found("No active TOS version found")

    return ok(_serialize(row))


# ─────────────────────────────────────────────────────────────────────────────
# MOBILE — GET ACTIVE TOS  (read-only, students)
# ─────────────────────────────────────────────────────────────────────────────

@mobile_tos_router.get("/active")
async def get_active_tos(request: Request):
    auth = login_required(request)

    row = fetchone("""
        SELECT id, label, academic_year, data, extracted_at, updated_at
        FROM tos_versions
        WHERE status = 'ACTIVE'
        ORDER BY updated_at DESC
        LIMIT 1
    """)

    if not row:
        return not_found("No active TOS version found")

    return ok(_serialize(row))