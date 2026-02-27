# BSPsych LMS — Flask REST API

A role-aware REST API for the BS Psychology Learning Management System, serving both a **web dashboard** (Admin & Faculty) and a **mobile app** (Students).

---

## Stack

| Layer | Technology |
|---|---|
| Framework | Flask 3.x |
| Database | PostgreSQL 14+ (psycopg2 connection pool) |
| Auth | JWT in HttpOnly cookies (Bearer header also accepted) |
| Password hashing | bcrypt |
| CORS | flask-cors with credentials support |
| Production server | Gunicorn |

---

## Project Structure

```
backend/
├── app/
│   ├── __init__.py              # App factory + blueprint registration
│   ├── db.py                    # Connection pool + helpers (fetchone, fetchall, paginate…)
│   ├── middleware/
│   │   └── auth.py              # JWT helpers, @login_required, @roles_required
│   ├── routes/
│   │   ├── auth.py              # /api/web/auth  +  /api/mobile/auth
│   │   ├── users.py             # /api/web/admin/users  +  /api/web/faculty/users
│   │   ├── whitelist.py         # /api/web/admin/whitelist  +  /api/web/faculty/whitelist
│   │   ├── subjects.py          # /api/web/admin/subjects  +  /api/web/faculty/subjects  +  /api/mobile/student/subjects
│   │   ├── content.py           # /api/web/admin/content  +  /api/web/faculty/content  +  /api/mobile/student/content
│   │   ├── assessments.py       # /api/web/admin/assessments  +  /api/web/faculty/assessments  +  /api/mobile/student/assessments
│   │   ├── analytics.py         # /api/web/admin  +  /api/web/faculty  +  /api/mobile/student  (dashboard + analytics)
│   │   ├── misc.py              # settings, logs, revisions, verification, roles
│   │   ├── modules.py           # /api/modules (file-based modules)
│   │   ├── questions.py         # /api/questions (question bank)
│   │   └── verification.py      # /api/verification (change-request workflow)
│   └── utils/
│       ├── responses.py         # ok(), error(), not_found()… uniform response envelope
│       ├── pagination.py        # get_page_params(), get_search(), get_filter()
│       ├── validators.py        # validate_email(), validate_password(), require_fields()
│       └── log.py               # log_action() — inserts to activity_logs silently
├── migrations/
│   ├── schema.sql               # Full DB schema (run first)
│   └── seed.sql                 # Initial dataset (run second)
├── .env                         # Local environment variables (not committed)
├── requirements.txt
├── run.py                       # Dev server entry point
└── wsgi.py                      # Gunicorn entry point
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Git

---

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd backend
```

---

### 2. Create and activate a virtual environment

```bash
# macOS / Linux
python -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

---

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

### 4. Configure environment variables

Copy the example and fill in your values:

```bash
cp .env.example .env
```

Open `.env` and set the following:

```env
# ── Database ──────────────────────────────────────────────────
DB_HOST=localhost
DB_PORT=5432
DB_NAME=psych_db
DB_USER=postgres
DB_PASSWORD=your_postgres_password

# ── Auth ──────────────────────────────────────────────────────
JWT_SECRET=replace_with_a_long_random_string_at_least_32_chars
JWT_ACCESS_EXPIRY_MINUTES=60
JWT_REFRESH_EXPIRY_DAYS=7

# ── App ───────────────────────────────────────────────────────
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=another_random_flask_secret
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

> **Important:** Never commit `.env` to version control. It is already listed in `.gitignore`.

---

### 5. Create the database

```bash
psql -U postgres -c "CREATE DATABASE psych_db;"
```

---

### 6. Run migrations and seed data

```bash
# Create all tables, views, functions, and triggers
psql -U postgres -d psych_db -f migrations/schema.sql

# Insert initial roles, users, subjects, assessments, and sample data
psql -U postgres -d psych_db -f migrations/seed.sql
```

The `schema.sql` starts with `DROP … CASCADE` statements so it is safe to re-run — it will wipe and recreate everything from scratch.

**Default seeded accounts:**

| Role | Email | Password |
|---|---|---|
| Admin | admin@ppri.edu | Admin@1234 |
| Faculty | faculty1@ppri.edu | Faculty@1234 |
| Faculty | faculty2@ppri.edu | Faculty@1234 |
| Student | student1@ppri.edu | Student@1234 |
| Student | student2@ppri.edu | Student@1234 |

---

### 7. Start the development server

```bash
python run.py
```

The API will be available at `http://localhost:5000`.

Verify it is running:
```bash
curl http://localhost:5000/health
# → {"status": "ok", "service": "psych-api"}
```

---

### 8. Production (Gunicorn)

```bash
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:application
```

Set `FLASK_ENV=production` in your `.env` — this enables the `Secure` flag on cookies automatically.

---

## Authentication

### How it works

| Cookie | JS-readable | Purpose |
|---|---|---|
| `access_token` | No (HttpOnly) | Sent automatically on every request; verified by the API |
| `refresh_token` | No (HttpOnly) | Long-lived; used only at `POST /refresh` to get a new access token |
| `user_role` | Yes | Non-sensitive; lets the frontend gate UI without an extra API call |

Both cookies and `Authorization: Bearer <token>` headers are accepted. Use the header for non-browser clients (mobile apps, Postman, etc.).

### Surfaces

The API has two separate surfaces based on role:

| Surface | Base URL | Allowed roles |
|---|---|---|
| Web (dashboard) | `/api/web/` | `ADMIN`, `FACULTY` |
| Mobile | `/api/mobile/` | `STUDENT` |

Logging into the wrong surface returns `403 WRONG_APP`.

---

## Response Format

Every response follows the same envelope:

**Success:**
```json
{
  "success": true,
  "message": "Success",
  "data": { ... }
}
```

**Error:**
```json
{
  "success": false,
  "message": "Descriptive error message"
}
```

**Paginated list:**
```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [ ... ],
    "total": 45,
    "page": 1,
    "per_page": 20,
    "pages": 3
  }
}
```

### Common query parameters (all list endpoints)

| Param | Type | Default | Description |
|---|---|---|---|
| `page` | int | `1` | Page number |
| `per_page` | int | `20` | Items per page (max 100) |
| `search` | string | — | Searches name / title / email |

---

## API Reference

---

### 🔐 Auth

#### Web — Admin & Faculty
```
POST   /api/web/auth/login
POST   /api/web/auth/register      ← Faculty self-registration (creates PENDING account)
POST   /api/web/auth/logout
POST   /api/web/auth/refresh
GET    /api/web/auth/me
```

#### Mobile — Students
```
POST   /api/mobile/auth/login
POST   /api/mobile/auth/register   ← Student self-registration (creates PENDING account)
POST   /api/mobile/auth/logout
POST   /api/mobile/auth/refresh
GET    /api/mobile/auth/me
```

**Login request body:**
```json
{
  "email": "admin@ppri.edu",
  "password": "Admin@1234"
}
```

**Login response `data`:**
```json
{
  "id": "10000000-0000-0000-0000-000000000001",
  "email": "admin@ppri.edu",
  "first_name": "Ana",
  "last_name": "Reyes",
  "role": "ADMIN",
  "institutional_id": "ADMIN-001"
}
```

**Register request body (Faculty or Student):**
```json
{
  "institutional_id": "FAC-2024-003",
  "first_name": "Juan",
  "middle_name": "Cruz",
  "last_name": "Dela Cruz",
  "email": "juan@ppri.edu",
  "password": "SecurePass@1",
  "department": "Clinical Psychology"
}
```

> Registration requires the email + institutional ID to exist in the `whitelist` table first. The created account starts as `PENDING` and must be activated by an Admin.

**`GET /api/web/auth/me` response `data`:**
```json
{
  "id": "10000000-0000-0000-0000-000000000002",
  "institutional_id": "FAC-2024-001",
  "first_name": "Marco",
  "middle_name": "Antonio",
  "last_name": "Santos",
  "email": "faculty1@ppri.edu",
  "department": "Developmental Psychology",
  "status": "ACTIVE",
  "date_created": "2024-09-01T08:00:00+00:00",
  "last_login": "2025-01-15T10:30:00+00:00",
  "role_id": "00000000-0000-0000-0000-000000000002",
  "role_name": "FACULTY",
  "permissions": ["create_content", "submit_content", "..."]
}
```

---

### 👥 Users

```
# Admin only
GET    /api/web/admin/users              list all users
GET    /api/web/admin/users/pending      list PENDING users awaiting approval
GET    /api/web/admin/users/<id>         get user detail
POST   /api/web/admin/users             create user
PUT    /api/web/admin/users/<id>         update user
PATCH  /api/web/admin/users/<id>/status  change status
DELETE /api/web/admin/users/<id>         delete user

# Faculty (read-only, students only)
GET    /api/web/faculty/users            list students
GET    /api/web/faculty/users/<id>       get student detail
```

**Filters on `GET /api/web/admin/users`:**
```
?search=garcia
?role=STUDENT              # ADMIN | FACULTY | STUDENT
?status=ACTIVE             # PENDING | ACTIVE | INACTIVE | DEACTIVATED
```

**Create user body (Admin):**
```json
{
  "institutional_id": "2025-PSY-010",
  "first_name": "Sofia",
  "last_name": "Aquino",
  "email": "sofia@ppri.edu",
  "password": "Welcome@1",
  "role": "STUDENT",
  "department": "BS Psychology",
  "status": "ACTIVE"
}
```

**Patch status body:**
```json
{ "status": "ACTIVE" }
```
> Valid statuses: `PENDING` | `ACTIVE` | `INACTIVE` | `DEACTIVATED`

**User object (response `data`):**
```json
{
  "id": "10000000-0000-0000-0000-000000000011",
  "institutional_id": "2024-PSY-001",
  "name": "Jose Miguel Garcia",
  "first_name": "Jose",
  "middle_name": "Miguel",
  "last_name": "Garcia",
  "email": "student1@ppri.edu",
  "role": "STUDENT",
  "role_id": "00000000-0000-0000-0000-000000000003",
  "department": "BS Psychology",
  "status": "ACTIVE",
  "last_login": "2025-01-10T09:00:00+00:00",
  "date_created": "2024-11-01T08:00:00+00:00"
}
```

---

### 📋 Whitelist

```
# Admin (any role)
GET    /api/web/admin/whitelist          list whitelist entries
POST   /api/web/admin/whitelist          add single entry
POST   /api/web/admin/whitelist/bulk     bulk import (JSON array or CSV upload)
PUT    /api/web/admin/whitelist/<id>     update entry
DELETE /api/web/admin/whitelist/<id>     remove entry

# Faculty (students only)
GET    /api/web/faculty/whitelist        list student whitelist entries
POST   /api/web/faculty/whitelist        add student entry
PUT    /api/web/faculty/whitelist/<id>   update student entry
DELETE /api/web/faculty/whitelist/<id>   remove student entry
```

**Filters on list:**
```
?search=garcia
?role=STUDENT              # Admin only
?status=PENDING            # PENDING | REGISTERED
```

**Add entry body:**
```json
{
  "first_name": "Sofia",
  "last_name": "Aquino",
  "institutional_id": "2025-PSY-010",
  "email": "sofia@ppri.edu",
  "role": "STUDENT"
}
```

**Bulk import — JSON body:**
```json
[
  { "first_name": "Ana", "last_name": "Cruz", "institutional_id": "2025-PSY-011", "email": "ana@ppri.edu", "role": "STUDENT" },
  { "first_name": "Ben", "last_name": "Lim",  "institutional_id": "2025-PSY-012", "email": "ben@ppri.edu", "role": "STUDENT" }
]
```

**Bulk import — CSV upload:**
```
POST /api/web/admin/whitelist/bulk
Content-Type: multipart/form-data

file: <your .csv file>
```
CSV must have headers: `first_name, last_name, institutional_id, email, role`

**Bulk response `data`:**
```json
{
  "added": 8,
  "failed": 1,
  "errors": [
    { "record": { "email": "duplicate@ppri.edu" }, "reason": "Email already whitelisted" }
  ]
}
```

**Whitelist entry object:**
```json
{
  "id": "20000000-0000-0000-0000-000000000011",
  "name": "Jose Miguel Garcia",
  "first_name": "Jose",
  "last_name": "Garcia",
  "institutional_id": "2024-PSY-001",
  "studentNumber": "2024-PSY-001",
  "email": "student1@ppri.edu",
  "role": "STUDENT",
  "status": "REGISTERED",
  "dateAdded": "2024-10-25T08:00:00+00:00"
}
```

---

### 📚 Subjects

```
# Admin
GET    /api/web/admin/subjects                         list all subjects
GET    /api/web/admin/subjects/<id>                    subject detail + full topic tree
POST   /api/web/admin/subjects                         create subject (auto-approved)
PUT    /api/web/admin/subjects/<id>                    update subject
DELETE /api/web/admin/subjects/<id>                    delete subject
GET    /api/web/admin/subjects/pending-changes         list pending faculty changes
PATCH  /api/web/admin/subjects/<change_id>/approve-change   approve or reject a faculty change

# Topic management (Admin)
POST   /api/web/admin/subjects/<id>/topics             add topic
PUT    /api/web/admin/subjects/<id>/topics/<topic_id>  update topic
DELETE /api/web/admin/subjects/<id>/topics/<topic_id>  delete topic

# Faculty (approved subjects only; edits go through pending change flow)
GET    /api/web/faculty/subjects
GET    /api/web/faculty/subjects/<id>
POST   /api/web/faculty/subjects/<id>/topics           add topic (PENDING)
PUT    /api/web/faculty/subjects/<id>/topics/<tid>     update topic (PENDING)
POST   /api/web/faculty/subjects/<id>/submit-change    submit full subject snapshot for review

# Mobile (read-only, approved only)
GET    /api/mobile/student/subjects
GET    /api/mobile/student/subjects/<id>
```

**Filters on list:**
```
?search=developmental
```

**Create subject body (Admin):**
```json
{
  "name": "Industrial-Organizational Psychology",
  "description": "Application of psychology in workplace settings.",
  "color": "#14b8a6"
}
```

**Add topic body:**
```json
{
  "title": "Job Analysis and Design",
  "description": "Methods for describing roles and structuring work.",
  "content": "Optional rich text content here.",
  "parent_id": null,
  "sort_order": 1
}
```

**Subject detail response `data`:**
```json
{
  "id": "30000000-0000-0000-0000-000000000001",
  "name": "General Psychology",
  "description": "Foundational concepts…",
  "color": "#6366f1",
  "status": "APPROVED",
  "topic_count": 10,
  "topics": [
    {
      "id": "40000000-0000-0000-0000-000000000001",
      "title": "History and Schools of Thought",
      "sort_order": 1,
      "status": "APPROVED",
      "subTopics": []
    }
  ]
}
```

**Approve/reject change body:**
```json
{
  "action": "APPROVE",
  "note": "Looks good, approved."
}
```

---

### 📄 Content Modules

```
# Admin
GET    /api/web/admin/content                  list all content
GET    /api/web/admin/content/<id>             get content detail
POST   /api/web/admin/content                  create (auto-approved)
PUT    /api/web/admin/content/<id>             update
PATCH  /api/web/admin/content/<id>/status      approve / reject / request revision
DELETE /api/web/admin/content/<id>             delete

# Faculty (own + approved content; drafts go through approval)
GET    /api/web/faculty/content
GET    /api/web/faculty/content/<id>
POST   /api/web/faculty/content                create (starts as DRAFT)
PUT    /api/web/faculty/content/<id>
PATCH  /api/web/faculty/content/<id>/submit    submit draft for admin review
PATCH  /api/web/faculty/content/<id>/request-removal
DELETE /api/web/faculty/content/<id>           delete own DRAFT/REJECTED only

# Mobile (approved content only + progress tracking)
GET    /api/mobile/student/content
GET    /api/mobile/student/content/<id>
POST   /api/mobile/student/content/<id>/complete   mark as read
```

**Filters on list:**
```
?search=neurons
?status=APPROVED           # DRAFT | PENDING | APPROVED | REVISION_REQUESTED | REJECTED | REMOVAL_PENDING
?subject_id=<uuid>
```

**Create/update content body:**
```json
{
  "title": "The Neuron: Structure and Function",
  "subject_id": "30000000-0000-0000-0000-000000000001",
  "topic_id": "40000000-0000-0000-0000-000000000004",
  "content": "Neurons are specialized cells…",
  "format": "TEXT",
  "file_url": null
}
```
> `format` values: `TEXT` | `PDF` | `VIDEO` | `LINK` | `IMAGE`

**Status update body (Admin):**
```json
{
  "status": "REVISION_REQUESTED",
  "note": "Please add diagrams and expand section 2."
}
```
> Valid status transitions: `APPROVED` | `REJECTED` | `REVISION_REQUESTED`

**Content module object:**
```json
{
  "id": "50000000-0000-0000-0000-000000000001",
  "title": "Introduction to Psychology: A Brief History",
  "subject_id": "30000000-0000-0000-0000-000000000001",
  "subject_name": "General Psychology",
  "topic_id": "40000000-0000-0000-0000-000000000001",
  "topic_title": "History and Schools of Thought",
  "content": "Psychology evolved from philosophy…",
  "format": "TEXT",
  "file_url": null,
  "status": "APPROVED",
  "revision_notes": [],
  "submission_count": 1,
  "author_id": "10000000-0000-0000-0000-000000000002",
  "author_name": "Marco Santos",
  "last_updated": "2024-09-20T00:00:00+00:00",
  "date_created": "2024-09-25T00:00:00+00:00"
}
```

**Mobile content detail** includes two extra fields:
```json
{
  "completed": true,
  "completed_at": "2024-11-20T14:00:00+00:00"
}
```

---

### 📝 Assessments

```
# Admin
GET    /api/web/admin/assessments                  list all assessments
GET    /api/web/admin/assessments/<id>             get with questions
POST   /api/web/admin/assessments                  create (auto-approved)
PUT    /api/web/admin/assessments/<id>             update
PATCH  /api/web/admin/assessments/<id>/status      approve / reject / revision
DELETE /api/web/admin/assessments/<id>             delete

# Faculty (own + approved; starts as DRAFT)
GET    /api/web/faculty/assessments
GET    /api/web/faculty/assessments/<id>
POST   /api/web/faculty/assessments
PUT    /api/web/faculty/assessments/<id>
PATCH  /api/web/faculty/assessments/<id>/submit    submit DRAFT for review
DELETE /api/web/faculty/assessments/<id>

# Mobile (approved only; submit answers)
GET    /api/mobile/student/assessments
GET    /api/mobile/student/assessments/<id>
POST   /api/mobile/student/assessments/<id>/submit
GET    /api/mobile/student/assessments/<id>/result
```

**Filters on list:**
```
?search=general
?type=QUIZ                 # PRE_ASSESSMENT | QUIZ | POST_ASSESSMENT
?status=APPROVED
?subject_id=<uuid>
```

**Create/update assessment body:**
```json
{
  "title": "Neurons and Neural Communication — Quiz",
  "type": "QUIZ",
  "subject_id": "30000000-0000-0000-0000-000000000001",
  "topic_id": "40000000-0000-0000-0000-000000000004",
  "questions": [
    {
      "id": "q001",
      "text": "What is the resting membrane potential of a neuron?",
      "options": ["-70 mV", "+70 mV", "-50 mV", "0 mV"],
      "answer": "-70 mV"
    },
    {
      "id": "q002",
      "text": "Which part receives incoming signals?",
      "options": ["Axon", "Dendrites", "Myelin sheath", "Soma"],
      "answer": "Dendrites"
    }
  ]
}
```
> Each question in the `questions` array must include `id`, `text`, `options` (array), and `answer` (exact text of the correct option). `items` is auto-calculated from the array length.

**Submit answers body (Mobile/Student):**
```json
{
  "answers": [
    { "question_id": "q001", "answer": "-70 mV" },
    { "question_id": "q002", "answer": "Dendrites" }
  ],
  "time_taken_s": 180
}
```

**Submit response `data`:**
```json
{
  "submission_id": "70000000-0000-0000-0001-000000000007",
  "score": 100.0,
  "passed": true,
  "correct_count": 2,
  "total_items": 2,
  "passing_grade": 75,
  "submitted_at": "2025-01-15T10:30:00+00:00"
}
```

**Get result response `data`:**
```json
{
  "id": "70000000-0000-0000-0001-000000000007",
  "assessment_id": "60000000-0000-0000-0000-000000000002",
  "student_id": "10000000-0000-0000-0000-000000000011",
  "score": 83.33,
  "passed": true,
  "correct": 5,
  "total": 6,
  "answers": [ { "question_id": "q001", "answer": "-70 mV", "correct": true } ],
  "time_taken_s": 510,
  "submitted_at": "2024-11-15T10:00:00+00:00"
}
```

---

### 📊 Dashboard & Analytics

#### Admin
```
GET  /api/web/admin/dashboard           overall platform stats
GET  /api/web/admin/analytics           paginated student list with scores
GET  /api/web/admin/analytics/<id>      full student record
```

**Dashboard response `data`:**
```json
{
  "totalStudents": 4,
  "totalFaculty": 2,
  "totalSubjects": 5,
  "totalModularUnits": 25,
  "totalMaterials": 9,
  "pendingApprovals": 3,
  "readinessAvg": 78.5,
  "systemStatus": "ACTIVE",
  "userGrowth": [
    { "date": "2025-01-09", "total": 1 },
    { "date": "2025-01-10", "total": 2 }
  ],
  "roleDistribution": [
    { "name": "STUDENT", "value": 4, "color": "#8b5cf6" },
    { "name": "FACULTY", "value": 2, "color": "#22c55e" },
    { "name": "ADMIN",   "value": 1, "color": "#ef4444" }
  ],
  "recentActivity": [
    {
      "id": "a0000000-...",
      "action": "Assessment submitted",
      "target": "General Psychology — Pre-Assessment",
      "user_name": "Jose Garcia",
      "created_at": "2025-01-15T10:30:00+00:00"
    }
  ]
}
```

**Analytics list response `data.items` entry:**
```json
{
  "id": "10000000-0000-0000-0000-000000000011",
  "name": "Jose Miguel Garcia",
  "email": "student1@ppri.edu",
  "institutional_id": "2024-PSY-001",
  "department": "BS Psychology",
  "overall_average": 78.9,
  "assessments_taken": 6,
  "readiness_probability": "MODERATE"
}
```

**Analytics detail response `data`:**
```json
{
  "id": "10000000-0000-0000-0000-000000000011",
  "name": "Jose Miguel Garcia",
  "email": "student1@ppri.edu",
  "institutional_id": "2024-PSY-001",
  "department": "BS Psychology",
  "readinessProbability": "MODERATE",
  "overallAverage": 75.6,
  "subjectScores": [
    { "subject": "General Psychology", "preScore": 60.0, "currentScore": 90.0, "fullMark": 100 }
  ],
  "assessmentsTaken": 6,
  "assessmentsPassed": 4,
  "mockExamHistory": [
    { "date": "Dec 27", "score": 90.0, "label": "General Psychology — Post-Assessment" }
  ],
  "materialsRead": 4,
  "totalMaterials": 9,
  "streak": 2,
  "totalStudyHours": 0.8,
  "platformLogins": 3,
  "enrollment_date": "2024-11-01T08:00:00+00:00"
}
```

#### Faculty
```
GET  /api/web/faculty/dashboard
GET  /api/web/faculty/analytics
GET  /api/web/faculty/analytics/<id>
```

**Faculty dashboard response `data`:**
```json
{
  "totalStudents": 4,
  "totalModules": 7,
  "totalSubjects": 5,
  "pendingRequests": 2,
  "systemStatus": "ACTIVE",
  "assessmentCounts": {
    "preAssessments": 2,
    "quizzes": 2,
    "postAssessments": 1
  }
}
```

#### Student (Mobile)
```
GET  /api/mobile/student/dashboard
GET  /api/mobile/student/progress
```

**Student dashboard response `data`:**
```json
{
  "student": {
    "id": "10000000-0000-0000-0000-000000000011",
    "first_name": "Jose",
    "last_name": "Garcia",
    "email": "student1@ppri.edu",
    "institutional_id": "2024-PSY-001",
    "department": "BS Psychology"
  },
  "overallReadiness": {
    "percentage": 75.6,
    "level": "MODERATE",
    "subject_scores": [
      { "subject": "General Psychology", "preScore": 60.0, "currentScore": 90.0, "fullMark": 100 }
    ]
  },
  "subjects": [
    {
      "id": "30000000-0000-0000-0000-000000000001",
      "name": "General Psychology",
      "color": "#6366f1",
      "completionPct": 44.4,
      "readinessScore": 90.0,
      "assessmentAvg": 77.8
    }
  ],
  "streak": 2
}
```

---

### ⚙️ System Settings

```
GET  /api/web/admin/settings
PUT  /api/web/admin/settings
```

**Settings object:**
```json
{
  "id": 1,
  "maintenance_mode": false,
  "maintenance_banner": null,
  "require_content_approval": true,
  "allow_public_registration": false,
  "institutional_passing_grade": 75,
  "institution_name": "Philippine Psychology Review Institute",
  "academic_year": "2024-2025",
  "updated_at": "2025-01-15T08:00:00+00:00"
}
```

**Update body (all fields optional):**
```json
{
  "maintenanceMode": true,
  "maintenanceBanner": "System under maintenance until 3PM.",
  "requireContentApproval": true,
  "allowPublicRegistration": false,
  "institutionalPassingGrade": 75,
  "institutionName": "Philippine Psychology Review Institute",
  "academicYear": "2025-2026"
}
```

---

### 📋 Revisions

```
# Admin
GET    /api/web/admin/revisions            list revisions (?status=PENDING|RESOLVED)
GET    /api/web/admin/revisions/<id>       get revision detail
PATCH  /api/web/admin/revisions/<id>/resolve  mark as resolved

# Faculty
GET    /api/web/faculty/revisions          list own pending revisions
POST   /api/web/faculty/revisions          create revision request
```

**Create revision body (Faculty):**
```json
{
  "target_type": "MODULE",
  "target_id": "50000000-0000-0000-0000-000000000003",
  "title": "Update neuron diagrams",
  "details": "Please add demyelinating disease examples."
}
```

---

### ✅ Verification (Pending Approval Queue)

```
GET  /api/web/admin/verification           all pending items (modules, assessments, subjects, users)
GET  /api/web/faculty/verification         faculty's own pending submissions
```

**Admin verification response `data`:**
```json
{
  "modules": [
    {
      "id": "50000000-...",
      "title": "Psychological Assessment Tools: MMPI and Rorschach",
      "status": "PENDING",
      "date": "2025-01-08T00:00:00+00:00",
      "author": "Elena Villanueva",
      "subject": "Psychological Assessment",
      "type": "Module"
    }
  ],
  "assessments": [ ... ],
  "subjects": [ ... ],
  "users": [ ... ]
}
```

Filter by type:
```
?type=modules       # modules | assessments | subjects | users | all (default)
```

---

### 🔒 Roles

```
GET    /api/web/admin/roles         list all roles
GET    /api/web/admin/roles/<id>    get role detail
POST   /api/web/admin/roles         create custom role
PUT    /api/web/admin/roles/<id>    update custom role
DELETE /api/web/admin/roles/<id>    delete custom role
```

> System roles (`ADMIN`, `FACULTY`, `STUDENT`) cannot be modified or deleted.

**Create/update role body:**
```json
{
  "name": "REVIEWER",
  "permissions": ["view_content", "view_analytics"]
}
```

---

### 📜 Activity Logs

```
GET  /api/web/admin/logs
```

**Filters:**
```
?search=submitted
?user_id=<uuid>
?from=2025-01-01
?to=2025-01-31
```

**Log entry object:**
```json
{
  "id": "a0000000-0000-0000-0000-000000000001",
  "action": "Assessment submitted",
  "target": "General Psychology — Pre-Assessment",
  "target_id": "60000000-...",
  "userName": "Jose Garcia",
  "user_id": "10000000-...",
  "ip_address": "127.0.0.1",
  "timestamp": "2025-01-15T10:30:00+00:00"
}
```

---

## HTTP Status Codes

| Code | Meaning |
|---|---|
| `200` | Success |
| `201` | Resource created |
| `204` | Success, no content (DELETE) |
| `400` | Bad request / validation error |
| `401` | Not authenticated |
| `403` | Forbidden (wrong role or wrong app surface) |
| `404` | Resource not found |
| `409` | Conflict (duplicate email, cannot delete approved resource, etc.) |
| `500` | Internal server error |
| `503` | System under maintenance |

---

## Security Notes

- Passwords are stored as bcrypt hashes (cost factor 12). Never stored in plain text.
- JWT secret must be set via `.env` — never hardcode it.
- Auth tokens use `HttpOnly; SameSite=Lax` cookies — inaccessible from JavaScript.
- `Secure` flag is auto-enabled when `FLASK_ENV=production`.
- Faculty can only modify, submit, or delete content and assessments they authored.
- Admin cannot delete their own account.
- Approved content and assessments cannot be deleted — only removal-requested or archived.
- Whitelist entries with status `REGISTERED` cannot be edited or deleted.
- Non-admin roles are blocked from all endpoints when maintenance mode is active (except login).