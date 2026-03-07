CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS roles (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(50) NOT NULL UNIQUE,
    permissions JSONB       NOT NULL DEFAULT '[]',
    is_system   BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    cvsu_id          VARCHAR(100),
    first_name       VARCHAR(100) NOT NULL,
    middle_name      VARCHAR(100),
    last_name        VARCHAR(100) NOT NULL,
    email            VARCHAR(255) NOT NULL UNIQUE,
    password         VARCHAR(255) NOT NULL,
    role_id          UUID         NOT NULL REFERENCES roles(id),

    status           VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE'
                     CHECK (status IN ('ACTIVE','REMOVED','PENDING')),

    department       VARCHAR(150),

    last_login       TIMESTAMPTZ,
    date_created     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email    ON users(LOWER(email));
CREATE INDEX IF NOT EXISTS idx_users_role_id  ON users(role_id);
CREATE INDEX IF NOT EXISTS idx_users_cvsu_id  ON users(cvsu_id);
CREATE INDEX IF NOT EXISTS idx_users_status   ON users(status);

CREATE TABLE IF NOT EXISTS subjects (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL UNIQUE,
    description TEXT,
    color       VARCHAR(20)  NOT NULL DEFAULT '#6366f1',
    weight      INT          DEFAULT 0,          -- NEW
    passing_rate INT         DEFAULT 75,         -- NEW
    status      VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING','APPROVED','REJECTED', 'REMOVED')),
    created_by  UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subjects_status ON subjects(status);
CREATE INDEX IF NOT EXISTS idx_subjects_creator ON subjects(created_by);

CREATE TABLE IF NOT EXISTS modules (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id  UUID        NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    parent_id   UUID        REFERENCES modules(id) ON DELETE CASCADE,
    title       VARCHAR(300) NOT NULL,
    description TEXT,
    content     TEXT,
    type        VARCHAR(10)  NOT NULL DEFAULT 'MODULE' CHECK (type IN ('MODULE', 'E-BOOK')), -- NEW: curriculum type
    format      VARCHAR(10)  NOT NULL DEFAULT 'TEXT' CHECK (format IN ('TEXT', 'PDF')),
    file_url    TEXT,
    file_name   VARCHAR(255),
    sort_order  INT          NOT NULL DEFAULT 0,
    status      VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING','APPROVED','REJECTED', 'REMOVED')),
    created_by  UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_modules_subject_id ON modules(subject_id);
CREATE INDEX IF NOT EXISTS idx_modules_parent_id  ON modules(parent_id);
CREATE INDEX IF NOT EXISTS idx_modules_creator ON modules(created_by);

CREATE TABLE IF NOT EXISTS assessments (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    title       VARCHAR(300) NOT NULL,

    type        VARCHAR(30)  NOT NULL
                CHECK (type IN (
                    'DIAGNOSTIC',
                    'PRE_ASSESSMENT',
                    'QUIZ',
                    'PRACTICE_TEST',
                    'MOCK_EXAM',
                    'POST_ASSESSMENT',
                    'FINAL_ASSESSMENT'
                )),

    subject_id  UUID         REFERENCES subjects(id)  ON DELETE SET NULL,
    module_id   UUID         REFERENCES modules(id)   ON DELETE SET NULL,
    
    items       INT          NOT NULL DEFAULT 0,

    status      VARCHAR(30)  NOT NULL DEFAULT 'DRAFT'
                CHECK (status IN (
                    'DRAFT','PENDING','APPROVED',
                    'REJECTED','REVISION_REQUESTED'
                )),

    author_id   UUID         REFERENCES users(id) ON DELETE SET NULL,

    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assessments_subject_id ON assessments(subject_id);
CREATE INDEX IF NOT EXISTS idx_assessments_type       ON assessments(type);
CREATE INDEX IF NOT EXISTS idx_assessments_status     ON assessments(status);
CREATE INDEX IF NOT EXISTS idx_assessments_author_id  ON assessments(author_id);

CREATE TABLE IF NOT EXISTS request_changes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_id UUID NOT NULL,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    type VARCHAR(20)  NOT NULL DEFAULT 'SUBJECT',
    CHECK (type IN ('SUBJECT','ASSESSMENT','QUESTION', 'MODULE')),
    content JSONB,
    revisions_list JSONB,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',        -- ADDED THIS
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),        -- ADDED THIS
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

CREATE INDEX IF NOT EXISTS idx_request_creator ON request_changes(created_by);
CREATE INDEX IF NOT EXISTS idx_request_type ON request_changes(type);
CREATE INDEX IF NOT EXISTS idx_request_status ON request_changes(status);

CREATE TABLE IF NOT EXISTS questions (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id      UUID        REFERENCES users(id) ON DELETE SET NULL,
    text           TEXT        NOT NULL,
	assessment_id UUID REFERENCES assessments(id) ON DELETE CASCADE,
    options        JSONB       NOT NULL DEFAULT '[]',
    correct_answer INT         NOT NULL DEFAULT 0,
    date_created   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS system_settings (
    id                          INT         PRIMARY KEY DEFAULT 1,
    maintenance_mode            BOOLEAN     NOT NULL DEFAULT FALSE,
    maintenance_banner          TEXT,
    require_content_approval    BOOLEAN     NOT NULL DEFAULT TRUE,
    allow_public_registration   BOOLEAN     NOT NULL DEFAULT FALSE,
    institutional_passing_grade INT         NOT NULL DEFAULT 75,
    institution_name            VARCHAR(300) NOT NULL DEFAULT 'Psychology Review Platform',
    academic_year               VARCHAR(20)  NOT NULL DEFAULT '2024-2025',
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT single_row CHECK (id = 1)
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(255) NOT NULL,
    target VARCHAR(255),
    target_id UUID,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_activity_logs_user ON activity_logs(user_id);
CREATE INDEX idx_activity_logs_date ON activity_logs(created_at);

CREATE OR REPLACE VIEW view_assessment_with_questions AS
SELECT 
    a.id AS assessment_id,
    a.title,
    a.type,
    a.status,
    a.items,
    a.subject_id,
    a.module_id,
    a.author_id AS assessment_author,
    a.created_at,
    -- Aggregate all related questions into a single JSON array
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'question_id', q.id,
                'text', q.text,
                'options', q.options,
                'correct_answer', q.correct_answer,
                'author_id', q.author_id
            ) ORDER BY q.date_created -- Ensures questions stay in order
        ) FILTER (WHERE q.id IS NOT NULL), 
        '[]'::jsonb
    ) AS questions_list
FROM 
    assessments a
LEFT JOIN 
    questions q ON a.id = q.assessment_id
GROUP BY 
    a.id;

CREATE OR REPLACE VIEW view_change_comparisons AS
SELECT 
    r.id AS request_id,
    r.target_id AS entity_id,
    r.type AS entity_module,
    r.content AS proposed_data,
    r.created_by,
    u.first_name || ' ' || u.last_name AS author_name,
    r.status,        
    r.created_at,    
    
    -- Dynamically fetch the live data based on the type of change
    CASE 
        WHEN r.type = 'MODULE' THEN 
            jsonb_build_object(
                'title', m.title,
                'description', m.description,
                'content', m.content,
                'format', m.format,
                'file_url', m.file_url,
                'file_name', m.file_name
            )
        WHEN r.type = 'SUBJECT' THEN 
            jsonb_build_object(
                'name', s.name,
                'description', s.description,
                'color', s.color,
                'weight', s.weight,
                'passingRate', s.passing_rate
            )
        WHEN r.type = 'ASSESSMENT' THEN 
            jsonb_build_object(
                'title', a.title,
                'type', a.type,
                'items', a.items
            )
        ELSE NULL 
    END AS live_data,
    
    COALESCE(m.subject_id, a.subject_id, s.id) AS subject_id

FROM request_changes r
LEFT JOIN users u ON r.created_by = u.id
LEFT JOIN modules m ON r.target_id = m.id AND r.type = 'MODULE'
LEFT JOIN subjects s ON r.target_id = s.id AND r.type = 'SUBJECT'
LEFT JOIN assessments a ON r.target_id = a.id AND r.type = 'ASSESSMENT';

CREATE TABLE IF NOT EXISTS assessment_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    assessment_id UUID REFERENCES assessments(id) ON DELETE CASCADE,
    
    score INT NOT NULL DEFAULT 0,
    total_items INT NOT NULL, -- Fetched from assessments.items at the time of taking
    
    date_taken TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_results_user ON assessment_results(user_id);

CREATE OR REPLACE VIEW view_student_individual_readiness AS
SELECT 
    u.id AS user_id,
    u.first_name,
    u.last_name,
    -- Calculate percentage: (Sum of all scores / Sum of all items) * 100
    ROUND(
        (SUM(ar.score)::NUMERIC / NULLIF(SUM(ar.total_items), 0)) * 100, 
    2) AS readiness_percentage
FROM 
    users u
INNER JOIN 
    roles r ON u.role_id = r.id
LEFT JOIN 
    assessment_results ar ON u.id = ar.user_id
WHERE 
    r.name ILIKE 'student' AND u.status = 'ACTIVE'
GROUP BY 
    u.id, u.first_name, u.last_name;

CREATE OR REPLACE VIEW view_general_readiness AS
SELECT 
    ROUND(AVG(readiness_percentage), 2) AS overall_system_readiness
FROM 
    view_student_individual_readiness
WHERE 
    readiness_percentage IS NOT NULL;

CREATE OR REPLACE VIEW view_admin_dashboard_stats AS
SELECT 
    -- 1. System Maintenance Status
    (SELECT maintenance_mode FROM system_settings WHERE id = 1) AS is_maintenance_mode,
    
    -- 2. Number of ACTIVE Students
    (SELECT COUNT(u.id) 
     FROM users u 
     INNER JOIN roles r ON u.role_id = r.id 
     WHERE r.name ILIKE 'student' AND u.status = 'ACTIVE') AS total_active_students,
     
    -- 3. Number of APPROVED Subjects
    (SELECT COUNT(id) 
     FROM subjects 
     WHERE status = 'APPROVED') AS total_approved_subjects,
     
    -- 4. Number of APPROVED Modules
    (SELECT COUNT(id) 
     FROM modules 
     WHERE status = 'APPROVED') AS total_approved_modules,

    -- 5. General Student Readiness (System-wide Average)
    (SELECT COALESCE(ROUND(AVG(readiness_percentage), 2), 0)
     FROM view_student_individual_readiness) AS general_student_readiness_avg;

-- AUTH function
-- 1. Create the Login Function
-- Verifies credentials for login. Only ACTIVE accounts may log in.
-- PENDING accounts (registered but awaiting admin approval) are explicitly blocked.
-- REMOVED accounts are also blocked.
CREATE OR REPLACE FUNCTION verify_user_login(
    p_email VARCHAR, 
    p_raw_password VARCHAR
)
RETURNS TABLE (
    user_id UUID, 
    first_name VARCHAR, 
    last_name VARCHAR, 
    role_id UUID,
    status VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        u.id, 
        u.first_name, 
        u.last_name, 
        u.role_id,
        u.status
    FROM 
        users u
    WHERE 
        LOWER(u.email) = LOWER(p_email)
        AND u.password = crypt(p_raw_password, u.password)
        AND u.status = 'ACTIVE'; -- Only ACTIVE users can log in; PENDING users must wait for admin approval
END;
$$ LANGUAGE plpgsql;
-- ── Whitelist table (pre-registration approval list) ─────────────────────────
-- This table stores entries added by admins/faculty BEFORE a user registers.
-- On registration, auth.py checks this table and marks status='REGISTERED'.
CREATE TABLE IF NOT EXISTS whitelist (
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

CREATE INDEX IF NOT EXISTS idx_whitelist_email  ON whitelist(LOWER(email));
CREATE INDEX IF NOT EXISTS idx_whitelist_status ON whitelist(status);
CREATE INDEX IF NOT EXISTS idx_whitelist_role   ON whitelist(role);

-- Backfill: replace legacy 'manage_whitelist' with granular permissions from permissions.ts
-- Runs safely on both fresh installs and upgraded DBs (idempotent).
UPDATE roles
SET permissions = permissions
    || '["view_whitelist","add_whitelist","edit_whitelist","delete_whitelist","cross_check_whitelist","students_whitelist_only"]'::jsonb
WHERE permissions @> '"manage_whitelist"'
  AND NOT (permissions @> '"view_whitelist"');
-- ── Sign-Up Feature: allow PENDING users to set their password via the web ────
-- The `can_signup` permission is stored in roles.permissions (JSONB).
-- A user pre-created by an Admin with status='PENDING' (no password yet) can
-- set their password by hitting POST /api/web/auth/signup if their role's
-- permissions array contains "can_signup".
--
-- IMPORTANT: After signup the user's status remains 'PENDING'.
-- They CANNOT log in until an admin explicitly sets their status to 'ACTIVE'
-- via the User Management page. The _do_login() guard enforces this.
--
-- password is nullable to support pre-created accounts that haven't signed up yet.
ALTER TABLE users ALTER COLUMN password DROP NOT NULL;

-- Index to efficiently look up pending users awaiting signup
CREATE INDEX IF NOT EXISTS idx_users_pending_signup
    ON users(status, LOWER(email))
    WHERE status = 'PENDING';

-- Grant can_signup to existing FACULTY and STUDENT roles that don't already have it
UPDATE roles
SET permissions = permissions || '["can_signup"]'::jsonb
WHERE name IN ('FACULTY', 'STUDENT')
  AND NOT (permissions @> '"can_signup"'::jsonb);

-- Note: approve_users was removed from permissions.ts. Approving accounts uses edit_users.
-- ── Registration tracking fields ──────────────────────────────────────────────
-- registration_type: how the account was created
--   'SELF_REGISTERED' = user filled the sign-up form themselves
--   'MANUALLY_ADDED'  = an admin or faculty added them via the admin panel
-- added_by:    FK to the admin/faculty who manually created the account (NULL for self-registered)
-- approved_by: FK to the admin who activated the PENDING account (NULL until approved)
-- approved_at: timestamp of when the account was approved

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS registration_type VARCHAR(20)
    DEFAULT 'MANUALLY_ADDED'
    CHECK (registration_type IN ('SELF_REGISTERED', 'MANUALLY_ADDED')),
  ADD COLUMN IF NOT EXISTS added_by   UUID REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_users_registration_type ON users(registration_type);
CREATE INDEX IF NOT EXISTS idx_users_added_by          ON users(added_by);
CREATE INDEX IF NOT EXISTS idx_users_approved_by       ON users(approved_by);
-- ── Student Mood Tracking ──────────────────────────────────────────────────────
-- Stores one mood entry per student per date (upsert on conflict).
-- mood_key matches the MoodKey type in mobile/constants/moods.ts:
--   joy | sad | anger | disgust | fear | anxiety | envy | ennui | embarrassment
-- source: 'home' = picked on the Home tab, 'calendar' = picked on the Calendar tab

CREATE TABLE IF NOT EXISTS student_moods (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mood_date  DATE        NOT NULL,
    mood_key   VARCHAR(20) NOT NULL
                CHECK (mood_key IN ('joy','sad','anger','disgust','fear','anxiety','envy','ennui','embarrassment')),
    source     VARCHAR(20) NOT NULL DEFAULT 'home'
                CHECK (source IN ('home','calendar')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, mood_date)
);

CREATE INDEX IF NOT EXISTS idx_student_moods_user    ON student_moods(user_id);
CREATE INDEX IF NOT EXISTS idx_student_moods_date    ON student_moods(mood_date);
CREATE INDEX IF NOT EXISTS idx_student_moods_key     ON student_moods(mood_key);
