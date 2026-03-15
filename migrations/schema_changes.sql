-- ============================================================
-- schema_changes.sql  —  Cognify  —  Schema Only
--
-- Execution order:
--   §0  DROP all tables   (clean slate every run)
--   §1  Extensions
--   §2  Tables            (FK-dependency order)
--   §3  Indexes
--   §4  Views             (CREATE OR REPLACE)
--   §5  Functions
--   §6  Role-permission backfills (idempotent UPDATEs)
--
-- Run this file FIRST, then run seed_changes.sql.
-- setup.py "Full Reset" executes both in that order automatically.
--
-- §0 drops every app table with CASCADE so FK constraints never
-- block the drop order. Extensions are kept (pgcrypto stays).
-- ============================================================


-- ============================================================
-- §0  DROP ALL TABLES  (reverse FK order, CASCADE for safety)
-- ============================================================

DROP TABLE IF EXISTS student_moods        CASCADE;
DROP TABLE IF EXISTS activity_logs        CASCADE;
DROP TABLE IF EXISTS announcements        CASCADE;
DROP TABLE IF EXISTS tos_versions         CASCADE;
DROP TABLE IF EXISTS assessment_results   CASCADE;
DROP TABLE IF EXISTS questions            CASCADE;
DROP TABLE IF EXISTS assessments          CASCADE;
DROP TABLE IF EXISTS request_changes      CASCADE;
DROP TABLE IF EXISTS modules              CASCADE;
DROP TABLE IF EXISTS subjects             CASCADE;
DROP TABLE IF EXISTS system_settings      CASCADE;
DROP TABLE IF EXISTS whitelist            CASCADE;
DROP TABLE IF EXISTS users                CASCADE;
DROP TABLE IF EXISTS roles                CASCADE;

-- Drop views explicitly (they survive table drops but are stale)
DROP VIEW IF EXISTS view_admin_dashboard_stats         CASCADE;
DROP VIEW IF EXISTS view_general_readiness             CASCADE;
DROP VIEW IF EXISTS view_student_individual_readiness  CASCADE;
DROP VIEW IF EXISTS view_change_comparisons            CASCADE;
DROP VIEW IF EXISTS view_assessment_with_questions     CASCADE;

-- Drop functions
DROP FUNCTION IF EXISTS verify_user_login(VARCHAR, VARCHAR) CASCADE;


-- ============================================================
-- §1  EXTENSIONS
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- ============================================================
-- §2  TABLES  (parents before children — FK order)
-- ============================================================

-- ── ROLES ────────────────────────────────────────────────────
CREATE TABLE roles (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(50) NOT NULL UNIQUE,
    permissions JSONB       NOT NULL DEFAULT '[]',
    is_system   BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── USERS ────────────────────────────────────────────────────
-- password nullable: pre-created accounts haven't signed up yet.
CREATE TABLE users (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    cvsu_id           VARCHAR(100),
    first_name        VARCHAR(100) NOT NULL,
    middle_name       VARCHAR(100),
    last_name         VARCHAR(100) NOT NULL,
    email             VARCHAR(255) NOT NULL UNIQUE,
    password          VARCHAR(255),
    role_id           UUID         NOT NULL REFERENCES roles(id),
    status            VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE'
                      CHECK (status IN ('ACTIVE','PENDING','REMOVED')),
    department        VARCHAR(150),
    registration_type VARCHAR(20)  DEFAULT 'MANUALLY_ADDED'
                      CHECK (registration_type IN ('SELF_REGISTERED','MANUALLY_ADDED')),
    added_by          UUID         REFERENCES users(id) ON DELETE SET NULL,
    approved_by       UUID         REFERENCES users(id) ON DELETE SET NULL,
    approved_at       TIMESTAMPTZ,
    username          VARCHAR(150),
    daily_goal        VARCHAR(100),
    personal_note     TEXT,
    last_login        TIMESTAMPTZ,
    date_created      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── WHITELIST ─────────────────────────────────────────────────
CREATE TABLE whitelist (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name       VARCHAR(100) NOT NULL,
    middle_name      VARCHAR(100),
    last_name        VARCHAR(100) NOT NULL,
    institutional_id VARCHAR(100) NOT NULL UNIQUE,
    email            VARCHAR(255) NOT NULL UNIQUE,
    role             VARCHAR(20)  NOT NULL DEFAULT 'STUDENT'
                     CHECK (role IN ('STUDENT','FACULTY','ADMIN')),
    status           VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING','REGISTERED')),
    added_by         UUID         REFERENCES users(id) ON DELETE SET NULL,
    date_added       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── SUBJECTS ──────────────────────────────────────────────────
CREATE TABLE subjects (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(200) NOT NULL UNIQUE,
    description  TEXT,
    color        VARCHAR(20)  NOT NULL DEFAULT '#6366f1',
    weight       INT          DEFAULT 0,
    passing_rate INT          DEFAULT 75,
    status       VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                 CHECK (status IN ('PENDING','APPROVED','REJECTED','REMOVED','REVISION_REQUESTED')),
    created_by   UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── MODULES ───────────────────────────────────────────────────
CREATE TABLE modules (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id  UUID         NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    parent_id   UUID         REFERENCES modules(id) ON DELETE CASCADE,
    title       VARCHAR(300) NOT NULL,
    description TEXT,
    content     TEXT,
    type        VARCHAR(10)  NOT NULL DEFAULT 'MODULE'
                CHECK (type IN ('MODULE','E-BOOK')),
    format      VARCHAR(10)  NOT NULL DEFAULT 'TEXT'
                CHECK (format IN ('TEXT','PDF')),
    file_url    TEXT,
    file_name   VARCHAR(255),
    sort_order  INT          NOT NULL DEFAULT 0,
    status      VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING','APPROVED','REJECTED','REMOVED','REVISION_REQUESTED')),
    created_by  UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── ASSESSMENTS ───────────────────────────────────────────────
CREATE TABLE assessments (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    title       VARCHAR(300) NOT NULL,
    type        VARCHAR(30)  NOT NULL
                CHECK (type IN (
                    'DIAGNOSTIC','PRE_ASSESSMENT','QUIZ',
                    'PRACTICE_TEST','MOCK_EXAM',
                    'POST_ASSESSMENT','FINAL_ASSESSMENT'
                )),
    subject_id  UUID         REFERENCES subjects(id)  ON DELETE SET NULL,
    module_id   UUID         REFERENCES modules(id)   ON DELETE SET NULL,
    items       INT          NOT NULL DEFAULT 0,
    status      VARCHAR(30)  NOT NULL DEFAULT 'DRAFT'
                CHECK (status IN ('DRAFT','PENDING','APPROVED','REJECTED','REVISION_REQUESTED')),
    author_id   UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── QUESTIONS ─────────────────────────────────────────────────
CREATE TABLE questions (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id      UUID        REFERENCES users(id) ON DELETE SET NULL,
    text           TEXT        NOT NULL,
    assessment_id  UUID        REFERENCES assessments(id) ON DELETE CASCADE,
    competency_codes JSONB NOT NULL DEFAULT '[]',
    options        JSONB       NOT NULL DEFAULT '[]',
    correct_answer INT         NOT NULL DEFAULT 0,
    date_created   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── ASSESSMENT RESULTS ────────────────────────────────────────
CREATE TABLE assessment_results (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID        REFERENCES users(id)       ON DELETE CASCADE,
    assessment_id UUID        REFERENCES assessments(id) ON DELETE CASCADE,
    score         INT         NOT NULL DEFAULT 0,
    total_items   INT         NOT NULL,
    date_taken    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── REQUEST CHANGES ───────────────────────────────────────────
CREATE TABLE request_changes (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    target_id      UUID        NOT NULL,
    created_by     UUID        REFERENCES users(id) ON DELETE SET NULL,
    type           VARCHAR(20) NOT NULL DEFAULT 'SUBJECT'
                   CHECK (type IN ('SUBJECT','ASSESSMENT','QUESTION','MODULE')),
    content        JSONB,
    revisions_list JSONB,
    status         VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT check_revisions_list_structure CHECK (
        revisions_list IS NULL OR (
            jsonb_typeof(revisions_list) = 'array' AND
            (jsonb_array_length(revisions_list) = 0 OR (
                revisions_list->0 ? 'notes' AND
                revisions_list->0 ? 'status' AND
                revisions_list->0 ? 'author_id'
            ))
        )
    )
);

-- ── SYSTEM SETTINGS ───────────────────────────────────────────
-- Single-row table; id = 1 enforced by CHECK constraint.
CREATE TABLE system_settings (
    id                          INT          PRIMARY KEY DEFAULT 1,
    maintenance_mode            BOOLEAN      NOT NULL DEFAULT FALSE,
    maintenance_banner          TEXT,
    require_content_approval    BOOLEAN      NOT NULL DEFAULT TRUE,
    allow_public_registration   BOOLEAN      NOT NULL DEFAULT FALSE,
    institutional_passing_grade INT          NOT NULL DEFAULT 75,
    institution_name            VARCHAR(300) NOT NULL DEFAULT 'Psychology Review Platform',
    academic_year               VARCHAR(20)  NOT NULL DEFAULT '2024-2025',
    updated_at                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT single_row CHECK (id = 1)
);

-- ── TOS VERSIONS ──────────────────────────────────────────────
-- Persists structured TOS data extracted from the board-exam PDF.
-- One ACTIVE version at a time; others are DRAFT or ARCHIVED.
--
-- `data` JSONB shape (matches extractor.py output envelope):
--   { "subjects": [ { "annex", "board", "subject", "weight",
--                     "sections": [...], "grand_total": {...} } ] }
--
-- status lifecycle:  DRAFT → ACTIVE → ARCHIVED
--   Only one row may be ACTIVE; activating a new one auto-archives
--   the previous one (enforced in app/routes/tos.py).
CREATE TABLE tos_versions (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    label             VARCHAR(200) NOT NULL,
    academic_year     VARCHAR(20)  NOT NULL DEFAULT '2024-2025',
    source_hash       VARCHAR(64),
    extraction_method VARCHAR(30)
                      CHECK (extraction_method IN ('llamaparse','geometry','manual')),
    extracted_at      TIMESTAMPTZ,
    data              JSONB        NOT NULL DEFAULT '{}',
    status            VARCHAR(20)  NOT NULL DEFAULT 'DRAFT'
                      CHECK (status IN ('DRAFT','ACTIVE','ARCHIVED')),
    notes             TEXT,
    created_by        UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── ACTIVITY LOGS ─────────────────────────────────────────────
CREATE TABLE activity_logs (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID         REFERENCES users(id) ON DELETE SET NULL,
    action     VARCHAR(255) NOT NULL,
    target     VARCHAR(255),
    target_id  UUID,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── ANNOUNCEMENTS ─────────────────────────────────────────────
CREATE TABLE announcements (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    title         VARCHAR(200) NOT NULL,
    body          TEXT         NOT NULL,
    type          VARCHAR(30)  NOT NULL DEFAULT 'INFO',
    audience      VARCHAR(20)  NOT NULL DEFAULT 'ALL',
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    tos_progress  INT          CHECK (tos_progress IS NULL OR (tos_progress >= 0 AND tos_progress <= 100)),
    expires_at    TIMESTAMPTZ,
    created_by    UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── STUDENT MOODS ─────────────────────────────────────────────
-- One mood entry per student per date; upsert on conflict.
CREATE TABLE student_moods (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mood_date  DATE        NOT NULL,
    mood_key   VARCHAR(20) NOT NULL
               CHECK (mood_key IN (
                   'joy','sad','anger','disgust','fear',
                   'anxiety','envy','ennui','embarrassment'
               )),
    source     VARCHAR(20) NOT NULL DEFAULT 'home'
               CHECK (source IN ('home','calendar')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, mood_date)
);


-- ============================================================
-- §3  INDEXES
-- ============================================================

CREATE INDEX idx_users_email             ON users(LOWER(email));
CREATE INDEX idx_users_role_id           ON users(role_id);
CREATE INDEX idx_users_cvsu_id           ON users(cvsu_id);
CREATE INDEX idx_users_status            ON users(status);
CREATE INDEX idx_users_registration_type ON users(registration_type);
CREATE INDEX idx_users_added_by          ON users(added_by);
CREATE INDEX idx_users_approved_by       ON users(approved_by);
CREATE INDEX idx_users_pending_signup    ON users(status, LOWER(email))
    WHERE status = 'PENDING';

CREATE INDEX idx_whitelist_email  ON whitelist(LOWER(email));
CREATE INDEX idx_whitelist_status ON whitelist(status);
CREATE INDEX idx_whitelist_role   ON whitelist(role);

CREATE INDEX idx_subjects_status  ON subjects(status);
CREATE INDEX idx_subjects_creator ON subjects(created_by);

CREATE INDEX idx_modules_subject_id ON modules(subject_id);
CREATE INDEX idx_modules_parent_id  ON modules(parent_id);
CREATE INDEX idx_modules_creator    ON modules(created_by);

CREATE INDEX idx_assessments_subject_id ON assessments(subject_id);
CREATE INDEX idx_assessments_type       ON assessments(type);
CREATE INDEX idx_assessments_status     ON assessments(status);
CREATE INDEX idx_assessments_author_id  ON assessments(author_id);

CREATE INDEX idx_results_user    ON assessment_results(user_id);

CREATE INDEX idx_request_creator ON request_changes(created_by);
CREATE INDEX idx_request_type    ON request_changes(type);
CREATE INDEX idx_request_status  ON request_changes(status);

CREATE INDEX idx_tos_versions_status        ON tos_versions(status);
CREATE INDEX idx_tos_versions_academic_year ON tos_versions(academic_year);
CREATE INDEX idx_tos_versions_created_by    ON tos_versions(created_by);

CREATE INDEX idx_activity_logs_user ON activity_logs(user_id);
CREATE INDEX idx_activity_logs_date ON activity_logs(created_at);

CREATE INDEX idx_announcements_active     ON announcements(is_active);
CREATE INDEX idx_announcements_created_at ON announcements(created_at DESC);
CREATE INDEX idx_announcements_audience   ON announcements(audience);

CREATE INDEX idx_student_moods_user ON student_moods(user_id);
CREATE INDEX idx_student_moods_date ON student_moods(mood_date);
CREATE INDEX idx_student_moods_key  ON student_moods(mood_key);

CREATE INDEX idx_questions_competency_codes ON questions USING gin(competency_codes);


-- ============================================================
-- §4  VIEWS
-- ============================================================

CREATE OR REPLACE VIEW view_assessment_with_questions AS
SELECT
    a.id   AS assessment_id,
    a.title,
    a.type,
    a.status,
    a.items,
    a.subject_id,
    a.module_id,
    a.author_id AS assessment_author,
    a.created_at,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'question_id',    q.id,
                'text',           q.text,
                'options',        q.options,
                'correct_answer', q.correct_answer,
                'author_id',      q.author_id
            ) ORDER BY q.date_created
        ) FILTER (WHERE q.id IS NOT NULL),
        '[]'::jsonb
    ) AS questions_list
FROM assessments a
LEFT JOIN questions q ON a.id = q.assessment_id
GROUP BY a.id;


CREATE OR REPLACE VIEW view_change_comparisons AS
SELECT
    r.id        AS request_id,
    r.target_id AS entity_id,
    r.type      AS entity_module,
    r.content   AS proposed_data,
    r.created_by,
    u.first_name || ' ' || u.last_name AS author_name,
    r.status,
    r.created_at,
    CASE
        WHEN r.type = 'MODULE' THEN
            jsonb_build_object(
                'title',       m.title,
                'description', m.description,
                'content',     m.content,
                'format',      m.format,
                'file_url',    m.file_url,
                'file_name',   m.file_name
            )
        WHEN r.type = 'SUBJECT' THEN
            jsonb_build_object(
                'name',        s.name,
                'description', s.description,
                'color',       s.color,
                'weight',      s.weight,
                'passingRate', s.passing_rate
            )
        WHEN r.type = 'ASSESSMENT' THEN
            jsonb_build_object(
                'title', a.title,
                'type',  a.type,
                'items', a.items
            )
        ELSE NULL
    END AS live_data,
    COALESCE(m.subject_id, a.subject_id, s.id) AS subject_id
FROM request_changes r
LEFT JOIN users       u ON r.created_by = u.id
LEFT JOIN modules     m ON r.target_id  = m.id AND r.type = 'MODULE'
LEFT JOIN subjects    s ON r.target_id  = s.id AND r.type = 'SUBJECT'
LEFT JOIN assessments a ON r.target_id  = a.id AND r.type = 'ASSESSMENT';


-- Mirrors _calc_readiness() in analytics.py exactly:
--   Step 1 — per student x subject x type: AVG((score/items)*100)
--             PRE_ASSESSMENT excluded (baseline, not a board score).
--   Step 2 — per student x subject: MAX across all non-pre types.
--   Step 3 — zero-fill: approved subjects with no results → 0.
--   Step 4 — overall = SUM(per-subject scores) / total_approved_subjects
CREATE OR REPLACE VIEW view_student_individual_readiness AS
WITH
approved_subjects AS (
    SELECT id, name FROM subjects WHERE status = 'APPROVED'
),
total_approved AS (
    SELECT COUNT(*) AS cnt FROM approved_subjects
),
type_avgs AS (
    SELECT
        ar.user_id,
        a.subject_id,
        AVG((ar.score::NUMERIC / NULLIF(ar.total_items, 0)) * 100) AS type_avg
    FROM  assessment_results ar
    JOIN  assessments a ON a.id = ar.assessment_id
    WHERE a.subject_id IN (SELECT id FROM approved_subjects)
      AND a.type <> 'PRE_ASSESSMENT'
    GROUP BY ar.user_id, a.subject_id, a.type
),
subject_best AS (
    SELECT
        user_id,
        subject_id,
        MAX(type_avg) AS subject_score
    FROM  type_avgs
    GROUP BY user_id, subject_id
)
SELECT
    u.id        AS user_id,
    u.first_name,
    u.last_name,
    ROUND(
        COALESCE(SUM(COALESCE(sb.subject_score, 0)), 0)::NUMERIC
        / NULLIF((SELECT cnt FROM total_approved), 0),
    1) AS readiness_percentage
FROM       users             u
JOIN       roles             r  ON r.id  = u.role_id
CROSS JOIN approved_subjects ap
LEFT  JOIN subject_best      sb ON sb.user_id    = u.id
                                AND sb.subject_id = ap.id
WHERE  r.name ILIKE 'student'
  AND  u.status = 'ACTIVE'
GROUP BY u.id, u.first_name, u.last_name;


CREATE OR REPLACE VIEW view_general_readiness AS
SELECT ROUND(AVG(readiness_percentage), 2) AS overall_system_readiness
FROM   view_student_individual_readiness
WHERE  readiness_percentage IS NOT NULL;


CREATE OR REPLACE VIEW view_admin_dashboard_stats AS
SELECT
    (SELECT maintenance_mode FROM system_settings WHERE id = 1)
        AS is_maintenance_mode,
    (SELECT COUNT(u.id)
     FROM users u INNER JOIN roles r ON u.role_id = r.id
     WHERE r.name ILIKE 'student' AND u.status = 'ACTIVE')
        AS total_active_students,
    (SELECT COUNT(id) FROM subjects WHERE status = 'APPROVED')
        AS total_approved_subjects,
    (SELECT COUNT(id) FROM modules WHERE status = 'APPROVED')
        AS total_approved_modules,
    (SELECT COALESCE(ROUND(AVG(readiness_percentage), 2), 0)
     FROM view_student_individual_readiness)
        AS general_student_readiness_avg;


-- ============================================================
-- §5  FUNCTIONS
-- ============================================================

-- verify_user_login: only ACTIVE accounts pass.
CREATE OR REPLACE FUNCTION verify_user_login(
    p_email        VARCHAR,
    p_raw_password VARCHAR
)
RETURNS TABLE (
    user_id    UUID,
    first_name VARCHAR,
    last_name  VARCHAR,
    role_id    UUID,
    status     VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT u.id, u.first_name, u.last_name, u.role_id, u.status
    FROM   users u
    WHERE  LOWER(u.email) = LOWER(p_email)
      AND  u.password = crypt(p_raw_password, u.password)
      AND  u.status = 'ACTIVE';
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- §6  ROLE-PERMISSION BACKFILLS  (idempotent — safe to re-run)
--     No-ops when the permissions are already correct.
-- ============================================================

-- Replace legacy 'manage_whitelist' with granular permissions
UPDATE roles
SET permissions = permissions
    || '["view_whitelist","add_whitelist","edit_whitelist","delete_whitelist","cross_check_whitelist","students_whitelist_only"]'::jsonb
WHERE permissions @> '"manage_whitelist"'
  AND NOT (permissions @> '"view_whitelist"');

-- Ensure FACULTY and STUDENT have can_signup
UPDATE roles
SET permissions = permissions || '["can_signup"]'::jsonb
WHERE name IN ('FACULTY','STUDENT')
  AND NOT (permissions @> '"can_signup"'::jsonb);

-- Ensure ADMIN has all four TOS permissions
UPDATE roles
SET permissions = permissions
    || '["view_tos","create_tos","edit_tos","delete_tos"]'::jsonb
WHERE name = 'ADMIN'
  AND NOT (permissions @> '"view_tos"'::jsonb);
-- Ensure FACULTY has view_student_analytics (pairs with view_analytics)
UPDATE roles
SET permissions = permissions || '["view_student_analytics"]'::jsonb
WHERE name = 'FACULTY'
  AND (permissions @> '"view_analytics"'::jsonb)
  AND NOT (permissions @> '"view_student_analytics"'::jsonb);

-- Ensure FACULTY and ADMIN have view_announcements
UPDATE roles
SET permissions = permissions || '["view_announcements"]'::jsonb
WHERE name IN ('FACULTY', 'ADMIN')
  AND NOT (permissions @> '"view_announcements"'::jsonb);