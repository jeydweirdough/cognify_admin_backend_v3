# BSPsych LMS — Flask REST API

A clean, role-aware REST API for the BS Psychology Learning Management System.

---

## Stack

| Layer | Technology |
|---|---|
| Framework | Flask 3.x |
| Database | PostgreSQL (psycopg2 connection pool) |
| Auth | JWT stored in HttpOnly cookies |
| Password | bcrypt |
| CORS | flask-cors with credentials support |
| Production | Gunicorn |

---

## Project Structure

```
psych_api/
├── app/
│   ├── __init__.py          # App factory, blueprint registration
│   ├── db.py                # Connection pool + query helpers (fetchone, paginate, …)
│   ├── middleware/
│   │   └── auth.py          # JWT issue/verify, @login_required, @roles_required
│   ├── routes/
│   │   ├── auth.py          # POST /login, /logout, /refresh  GET /me
│   │   ├── users.py         # Full user CRUD + whitelist approval
│   │   ├── subjects.py      # Subject CRUD + enrollment management
│   │   ├── modules.py       # Module CRUD
│   │   ├── assessments.py   # Assessment CRUD + question linking + results
│   │   ├── questions.py     # Question bank CRUD
│   │   ├── verification.py  # Change-request workflow (submit → review)
│   │   └── dashboard.py     # Admin dashboard + system settings
│   └── utils/
│       ├── responses.py     # ok(), error(), not_found(), … helpers
│       └── pagination.py    # get_page_params(), get_search()
├── .env.example
├── requirements.txt
├── run.py                   # Dev server
└── wsgi.py                  # Gunicorn entry point
```

---

## Setup

### 1. Clone & enter directory
```bash
git clone <repo>
cd cognify_admin_backend_v3
```

### 2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env with your Postgres credentials and secrets
```

**.env fields:**
```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=psych_db
DB_USER=postgres
DB_PASSWORD=yourpassword

JWT_SECRET=change_me_to_something_long_and_random
JWT_ACCESS_EXPIRY_MINUTES=60
JWT_REFRESH_EXPIRY_DAYS=7

FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=another_secret
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

### 4. Create the database and run migrations
```bash
psql -U postgres -c "CREATE DATABASE psych_db;"
psql -U postgres -d psych_db -f migrations/schema.sql
psql -U postgres -d psych_db -f migrations/seed.sql
```

### 5. Run development server
```bash
python run.py
# API available at http://localhost:5000
```

### 6. Run in production (Gunicorn)
```bash
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:application
```

---

## Authentication

### Strategy

| Token | Storage | Why |
|---|---|---|
| `access_token` | HttpOnly cookie | Prevents XSS; auto-sent on every request |
| `refresh_token` | HttpOnly cookie | Long-lived; used only to renew access token |
| `user_role` | Readable cookie | Non-sensitive; lets frontend gate UI without an extra API call |
| Preferences (theme, locale) | `localStorage` on client | Not sensitive; no integrity risk |

The HttpOnly flag means JavaScript **cannot** read auth tokens — they travel automatically in cookies. If you're building a non-browser client (e.g. mobile app or Swagger), pass `Authorization: Bearer <token>` as a header instead — both are supported.

### Endpoints

| Method | URL | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/login` | Public | Returns cookies + user info |
| `POST` | `/api/auth/logout` | Any | Clears cookies |
| `POST` | `/api/auth/refresh` | Cookie | Renews access token |
| `GET` | `/api/auth/me` | Any logged-in | Current user profile |

### Login example
```bash
curl -c cookies.txt -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"maria.reyes@cvsu-bacoor.edu.ph","password":"password123"}'
```

---

## Roles & Permissions

| Role | Capabilities |
|---|---|
| `ADMIN` | Full CRUD on everything; approve/reject users and change requests |
| `FACULTY` | Create/edit own subjects, modules, assessments, questions; submit change requests |
| `STUDENT` | Read enrolled subjects/modules; take assessments; view own results |

---

## API Reference

All responses follow:
```json
{
  "success": true,
  "message": "Success",
  "data": { ... }
}
```

Paginated responses wrap items:
```json
{
  "success": true,
  "data": {
    "items": [...],
    "total": 45,
    "page": 1,
    "per_page": 20,
    "pages": 3
  }
}
```

### Common query parameters
| Param | Description |
|---|---|
| `page` | Page number (default: 1) |
| `per_page` | Items per page (default: 20, max: 100) |
| `search` | Full-text search on name/title/email |

---

### Users `/api/users`

| Method | URL | Role | Description |
|---|---|---|---|
| `GET` | `/api/users/` | ADMIN | List all registered users. Filter: `?role=STUDENT&status=ACTIVE&search=juan` |
| `GET` | `/api/users/pending` | ADMIN | List pending (whitelist) users |
| `GET` | `/api/users/<id>` | ADMIN or own | View profile |
| `POST` | `/api/users/` | ADMIN | Create user |
| `PUT` | `/api/users/<id>` | ADMIN or own | Update profile (admin can also change role/status) |
| `PATCH` | `/api/users/<id>/approve` | ADMIN | Approve PENDING user → ACTIVE |
| `DELETE` | `/api/users/<id>` | ADMIN | Deactivate user (soft delete) |
| `GET` | `/api/users/roles/list` | ADMIN | List all roles |

**Create user body:**
```json
{
  "first_name": "Juan",
  "last_name": "Dela Cruz",
  "email": "juan@student.cvsu-bacoor.edu.ph",
  "password": "SecurePass123",
  "role_id": "aa000000-0000-0000-0000-000000000003",
  "department": "BSPsych",
  "status": "ACTIVE"
}
```

---

### Subjects `/api/subjects`

| Method | URL | Role | Description |
|---|---|---|---|
| `GET` | `/api/subjects/` | All | List subjects (students: enrolled only) |
| `GET` | `/api/subjects/<id>` | All | Detail with modules JSON |
| `POST` | `/api/subjects/` | ADMIN, FACULTY | Create (faculty → DRAFT) |
| `PUT` | `/api/subjects/<id>` | ADMIN, FACULTY(own) | Update |
| `DELETE` | `/api/subjects/<id>` | ADMIN | Archive |
| `GET` | `/api/subjects/<id>/enrollments` | ADMIN, FACULTY | List enrollments |
| `POST` | `/api/subjects/<id>/enrollments` | ADMIN, FACULTY | Enroll student |
| `DELETE` | `/api/subjects/<id>/enrollments/<student_id>` | ADMIN, FACULTY | Unenroll |

---

### Modules `/api/modules`

| Method | URL | Role | Description |
|---|---|---|---|
| `GET` | `/api/modules/?subject_id=<id>` | All | List modules |
| `GET` | `/api/modules/<id>` | All | Module detail |
| `POST` | `/api/modules/` | ADMIN, FACULTY | Create |
| `PUT` | `/api/modules/<id>` | ADMIN, FACULTY(own) | Update |
| `DELETE` | `/api/modules/<id>` | ADMIN | Archive |

---

### Assessments `/api/assessments`

| Method | URL | Role | Description |
|---|---|---|---|
| `GET` | `/api/assessments/` | All | List. Filter: `?subject_id=&type=QUIZ` |
| `GET` | `/api/assessments/<id>` | All | Detail with questions (students: no correct_answer) |
| `POST` | `/api/assessments/` | ADMIN, FACULTY | Create |
| `PUT` | `/api/assessments/<id>` | ADMIN, FACULTY(own) | Update |
| `DELETE` | `/api/assessments/<id>` | ADMIN | Archive |
| `POST` | `/api/assessments/<id>/questions` | ADMIN, FACULTY | Link questions: `{"question_ids": [...]}` |
| `DELETE` | `/api/assessments/<id>/questions/<qid>` | ADMIN, FACULTY | Unlink question |
| `GET` | `/api/assessments/<id>/results` | All | Results (students: own only) |
| `POST` | `/api/assessments/<id>/results` | STUDENT | Submit result: `{"score":4,"out_of":5}` |

---

### Questions `/api/questions`

| Method | URL | Role | Description |
|---|---|---|---|
| `GET` | `/api/questions/` | ADMIN, FACULTY | List (faculty: own only) |
| `GET` | `/api/questions/<id>` | ADMIN, FACULTY | Detail |
| `POST` | `/api/questions/` | ADMIN, FACULTY | Create |
| `PUT` | `/api/questions/<id>` | ADMIN, FACULTY(own) | Update |
| `DELETE` | `/api/questions/<id>` | ADMIN | Delete |

**Create question body:**
```json
{
  "text": "Which theorist proposed the zone of proximal development?",
  "options": ["Piaget", "Freud", "Vygotsky", "Erikson"],
  "correct_answer": 2
}
```

---

### Verification `/api/verification`

| Method | URL | Role | Description |
|---|---|---|---|
| `GET` | `/api/verification/summary` | ADMIN | Badge counts by category |
| `GET` | `/api/verification/queue` | ADMIN | Pending requests. Filter: `?category=SUBJECT&status=PENDING` |
| `GET` | `/api/verification/<id>` | ADMIN, FACULTY(own) | Full review detail |
| `POST` | `/api/verification/` | FACULTY, ADMIN | Submit change request |
| `PATCH` | `/api/verification/<id>/review` | ADMIN | Approve/reject: `{"status":"APPROVED","note":"Looks good"}` |
| `GET` | `/api/verification/my-requests` | Any | Own submitted requests |

---

### Dashboard `/api/dashboard`

| Method | URL | Role | Description |
|---|---|---|---|
| `GET` | `/api/dashboard/` | ADMIN | Full overview (subjects, users, modules, growth) |
| `GET` | `/api/dashboard/settings` | ADMIN | System settings |
| `PUT` | `/api/dashboard/settings` | ADMIN | Update settings |

---

## DRY Patterns Used

- **`db.py`** — all queries go through `fetchone`, `fetchall`, `execute_returning`, `paginate`. No raw psycopg2 scattered across routes.
- **`responses.py`** — `ok()`, `error()`, `not_found()`, etc. — consistent envelope everywhere.
- **`pagination.py`** — `get_page_params()` and `get_search()` — no duplicated query param parsing.
- **`auth.py` decorators** — `@login_required`, `@roles_required(...)`, `@owner_or_admin(...)` compose cleanly.
- **App factory** — `create_app()` registers all blueprints in a loop; adding a new blueprint is one line.

---

## Security Notes

- Passwords are stored as bcrypt hashes (cost factor 12).
- JWT secret must be set via environment variable — never hardcode.
- Auth tokens live in `HttpOnly; SameSite=Lax` cookies — not accessible from JavaScript.
- `Secure` flag is auto-enabled when `FLASK_ENV=production`.
- Students cannot see `correct_answer` in assessment detail responses.
- Faculty can only modify resources they authored.
- ADMIN cannot deactivate themselves.
