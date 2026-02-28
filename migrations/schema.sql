-- ============================================================
-- schema.sql
-- PostgreSQL 14+
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- DROP everything (views → tables → functions → triggers)
-- ────────────────────────────────────────────────────────────

-- Views
DROP VIEW IF EXISTS v_activity_feed             CASCADE;
DROP VIEW IF EXISTS v_subject_stats             CASCADE;
DROP VIEW IF EXISTS v_whitelist_with_user       CASCADE;
DROP VIEW IF EXISTS v_review_detail             CASCADE;
DROP VIEW IF EXISTS v_verification_summary      CASCADE;
DROP VIEW IF EXISTS v_content_with_meta         CASCADE;
DROP VIEW IF EXISTS v_assessment_with_meta      CASCADE;
DROP VIEW IF EXISTS v_student_summary           CASCADE;
DROP VIEW IF EXISTS v_dashboard_overview        CASCADE;

-- Tables (child → parent order)
DROP TABLE IF EXISTS enrollments                CASCADE;
DROP TABLE IF EXISTS student_progress           CASCADE;
DROP TABLE IF EXISTS assessment_submissions     CASCADE;
DROP TABLE IF EXISTS assessments                CASCADE;
DROP TABLE IF EXISTS modules                    CASCADE;
DROP TABLE IF EXISTS questions                  CASCADE;
DROP TABLE IF EXISTS content_modules            CASCADE;
DROP TABLE IF EXISTS request_changes            CASCADE;
DROP TABLE IF EXISTS revisions                  CASCADE;
DROP TABLE IF EXISTS pending_subject_changes    CASCADE;
DROP TABLE IF EXISTS topics                     CASCADE;
DROP TABLE IF EXISTS subjects                   CASCADE;
DROP TABLE IF EXISTS activity_logs              CASCADE;
DROP TABLE IF EXISTS system_settings            CASCADE;
DROP TABLE IF EXISTS whitelist                  CASCADE;
DROP TABLE IF EXISTS users                      CASCADE;
DROP TABLE IF EXISTS roles                      CASCADE;

-- Functions
DROP FUNCTION IF EXISTS calc_readiness(UUID)    CASCADE;
DROP FUNCTION IF EXISTS overall_readiness_level(NUMERIC) CASCADE;
DROP FUNCTION IF EXISTS student_streak(UUID)    CASCADE;
DROP FUNCTION IF EXISTS pending_approval_count() CASCADE;
DROP FUNCTION IF EXISTS set_updated_at()        CASCADE;
DROP FUNCTION IF EXISTS set_last_updated()      CASCADE;

-- Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()

-- ────────────────────────────────────────────────────────────
-- 1. ROLES
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS roles (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(50) NOT NULL UNIQUE,
    permissions JSONB       NOT NULL DEFAULT '[]',
    is_system   BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- 2. USERS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    institutional_id VARCHAR(50) NOT NULL,
    first_name       VARCHAR(100) NOT NULL,
    middle_name      VARCHAR(100),
    last_name        VARCHAR(100) NOT NULL,
    email            VARCHAR(255) NOT NULL UNIQUE,
    password         VARCHAR(255) NOT NULL,
    role_id          UUID         NOT NULL REFERENCES roles(id),
    status           VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING','ACTIVE','INACTIVE','DEACTIVATED')),
    department       VARCHAR(150),
    last_login       TIMESTAMPTZ,
    date_created     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email    ON users(LOWER(email));
CREATE INDEX IF NOT EXISTS idx_users_role_id  ON users(role_id);
CREATE INDEX IF NOT EXISTS idx_users_status   ON users(status);

-- ────────────────────────────────────────────────────────────
-- 3. WHITELIST
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS whitelist (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name       VARCHAR(100) NOT NULL,
    middle_name      VARCHAR(100),
    last_name        VARCHAR(100) NOT NULL,
    institutional_id VARCHAR(50)  NOT NULL,
    email            VARCHAR(255) NOT NULL UNIQUE,
    role             VARCHAR(20)  NOT NULL
                     CHECK (role IN ('ADMIN','FACULTY','STUDENT')),
    status           VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING','REGISTERED')),
    added_by         UUID         REFERENCES users(id) ON DELETE SET NULL,
    date_added       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_whitelist_email ON whitelist(LOWER(email));

-- ────────────────────────────────────────────────────────────
-- 4. SUBJECTS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS subjects (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL UNIQUE,
    description TEXT,
    color       VARCHAR(20)  NOT NULL DEFAULT '#6366f1',
    status      VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING','APPROVED','REJECTED')),
    created_by  UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subjects_status ON subjects(status);

-- ────────────────────────────────────────────────────────────
-- 5. TOPICS  (hierarchical: topic → subtopic)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS topics (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id  UUID        NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    parent_id   UUID        REFERENCES topics(id) ON DELETE CASCADE,
    title       VARCHAR(300) NOT NULL,
    description TEXT,
    content     TEXT,
    sort_order  INT          NOT NULL DEFAULT 0,
    status      VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING','APPROVED','REJECTED')),
    created_by  UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_topics_subject_id ON topics(subject_id);
CREATE INDEX IF NOT EXISTS idx_topics_parent_id  ON topics(parent_id);

-- ────────────────────────────────────────────────────────────
-- 6. PENDING SUBJECT CHANGES  (faculty → admin review)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pending_subject_changes (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id   UUID        NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    change_data  JSONB       NOT NULL DEFAULT '{}',
    status       VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                 CHECK (status IN ('PENDING','APPROVE','REJECT')),
    submitted_by UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reviewed_by  UUID        REFERENCES users(id) ON DELETE SET NULL,
    review_note  TEXT,
    reviewed_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- 7. CONTENT MODULES
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS content_modules (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    title            VARCHAR(300) NOT NULL,
    subject_id       UUID         REFERENCES subjects(id) ON DELETE SET NULL,
    topic_id         UUID         REFERENCES topics(id)   ON DELETE SET NULL,
    content          TEXT,
    format           VARCHAR(20)  NOT NULL DEFAULT 'TEXT'
                     CHECK (format IN ('TEXT','PDF','VIDEO','LINK','IMAGE')),
    file_url         TEXT,
    status           VARCHAR(30)  NOT NULL DEFAULT 'DRAFT'
                     CHECK (status IN (
                         'DRAFT','PENDING','APPROVED',
                         'REVISION_REQUESTED','REJECTED','REMOVAL_PENDING'
                     )),
    revision_notes   JSONB        NOT NULL DEFAULT '[]',
    submission_count INT          NOT NULL DEFAULT 0,
    author_id        UUID         REFERENCES users(id) ON DELETE SET NULL,
    author_name      VARCHAR(200),
    last_updated     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    date_created     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_content_subject_id ON content_modules(subject_id);
CREATE INDEX IF NOT EXISTS idx_content_status     ON content_modules(status);
CREATE INDEX IF NOT EXISTS idx_content_author_id  ON content_modules(author_id);

-- ────────────────────────────────────────────────────────────
-- 8. ASSESSMENTS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS assessments (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    title       VARCHAR(300) NOT NULL,
    type        VARCHAR(30)  NOT NULL
                CHECK (type IN ('PRE_ASSESSMENT','QUIZ','POST_ASSESSMENT')),
    subject_id  UUID         REFERENCES subjects(id)  ON DELETE SET NULL,
    topic_id    UUID         REFERENCES topics(id)    ON DELETE SET NULL,
    questions   JSONB        NOT NULL DEFAULT '[]',
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

-- ────────────────────────────────────────────────────────────
-- 9. ASSESSMENT SUBMISSIONS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS assessment_submissions (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id UUID        NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    student_id    UUID        NOT NULL REFERENCES users(id)       ON DELETE CASCADE,
    score         NUMERIC(6,2) NOT NULL DEFAULT 0,
    passed        BOOLEAN      NOT NULL DEFAULT FALSE,
    correct       INT          NOT NULL DEFAULT 0,
    total         INT          NOT NULL DEFAULT 0,
    answers       JSONB        NOT NULL DEFAULT '[]',
    time_taken_s  INT,
    submitted_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_submissions_student_id    ON assessment_submissions(student_id);
CREATE INDEX IF NOT EXISTS idx_submissions_assessment_id ON assessment_submissions(assessment_id);
CREATE INDEX IF NOT EXISTS idx_submissions_submitted_at  ON assessment_submissions(submitted_at);

-- ────────────────────────────────────────────────────────────
-- 10. STUDENT PROGRESS  (content read tracking)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS student_progress (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id   UUID        NOT NULL REFERENCES users(id)          ON DELETE CASCADE,
    content_id   UUID        NOT NULL REFERENCES content_modules(id) ON DELETE CASCADE,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (student_id, content_id)
);

CREATE INDEX IF NOT EXISTS idx_progress_student_id ON student_progress(student_id);

-- ────────────────────────────────────────────────────────────
-- 11. REVISIONS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS revisions (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type VARCHAR(30),
    target_id   UUID,
    title       VARCHAR(300),
    details     TEXT,
    category    VARCHAR(30),
    notes       JSONB       NOT NULL DEFAULT '[]',
    status      VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING','RESOLVED')),
    note        TEXT,
    author_id   UUID        REFERENCES users(id) ON DELETE SET NULL,
    created_by  UUID        REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- 12. REQUEST CHANGES  (verification workflow)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS request_changes (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id        UUID        REFERENCES users(id) ON DELETE SET NULL,
    changes_summary  JSONB       NOT NULL DEFAULT '{}',
    type             VARCHAR(20) NOT NULL CHECK (type IN ('ADD','UPDATE','REMOVE')),
    category         VARCHAR(20) NOT NULL CHECK (category IN ('SUBJECT','MODULE','ASSESSMENT','QUESTION')),
    status           VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING','APPROVED','REJECTED')),
    revision_id      UUID        REFERENCES revisions(id) ON DELETE SET NULL,
    date_created     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- 13. ACTIVITY LOGS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activity_logs (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        REFERENCES users(id) ON DELETE SET NULL,
    action      VARCHAR(300) NOT NULL,
    target      VARCHAR(300),
    target_id   VARCHAR(100),
    ip_address  VARCHAR(50),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activity_user_id    ON activity_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_created_at ON activity_logs(created_at DESC);

-- ────────────────────────────────────────────────────────────
-- 14. SYSTEM SETTINGS  (single-row config)
-- ────────────────────────────────────────────────────────────
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

-- ────────────────────────────────────────────────────────────
-- 15. QUESTIONS BANK  (legacy / standalone bank)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS questions (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id      UUID        REFERENCES users(id) ON DELETE SET NULL,
    text           TEXT        NOT NULL,
    options        JSONB       NOT NULL DEFAULT '[]',
    correct_answer INT         NOT NULL DEFAULT 0,
    date_created   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- 16. MODULES  (file-based modules within subjects)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS modules (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id   UUID        REFERENCES subjects(id) ON DELETE CASCADE,
    parent_id    UUID        REFERENCES modules(id)  ON DELETE SET NULL,
    author_id    UUID        REFERENCES users(id)    ON DELETE SET NULL,
    title        VARCHAR(300) NOT NULL,
    file_name    VARCHAR(300),
    file_url     TEXT,
    content      TEXT,
    format       VARCHAR(20)  NOT NULL DEFAULT 'PDF'
                 CHECK (format IN ('PDF','VIDEO','TEXT','LINK','IMAGE')),
    status       VARCHAR(20)  NOT NULL DEFAULT 'DRAFT'
                 CHECK (status IN ('DRAFT','PENDING','APPROVED','ARCHIVED')),
    date_created TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_updated TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_modules_subject_id ON modules(subject_id);
CREATE INDEX IF NOT EXISTS idx_modules_author_id  ON modules(author_id);

-- ────────────────────────────────────────────────────────────
-- 17. ENROLLMENTS  (student ↔ subject)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS enrollments (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID        NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    subject_id UUID        NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    status     VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
               CHECK (status IN ('ACTIVE','DROPPED','COMPLETED')),
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (student_id, subject_id)
);

CREATE INDEX IF NOT EXISTS idx_enrollments_student_id ON enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_subject_id ON enrollments(subject_id);


-- ============================================================
-- AUTO-UPDATE TRIGGERS
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION set_last_updated()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.last_updated = NOW();
    RETURN NEW;
END;
$$;

-- Subjects
DROP TRIGGER IF EXISTS trg_subjects_updated_at ON subjects;
CREATE TRIGGER trg_subjects_updated_at
    BEFORE UPDATE ON subjects
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Topics
DROP TRIGGER IF EXISTS trg_topics_updated_at ON topics;
CREATE TRIGGER trg_topics_updated_at
    BEFORE UPDATE ON topics
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Assessments
DROP TRIGGER IF EXISTS trg_assessments_updated_at ON assessments;
CREATE TRIGGER trg_assessments_updated_at
    BEFORE UPDATE ON assessments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Content modules
DROP TRIGGER IF EXISTS trg_content_modules_last_updated ON content_modules;
CREATE TRIGGER trg_content_modules_last_updated
    BEFORE UPDATE ON content_modules
    FOR EACH ROW EXECUTE FUNCTION set_last_updated();

-- Modules
DROP TRIGGER IF EXISTS trg_modules_last_updated ON modules;
CREATE TRIGGER trg_modules_last_updated
    BEFORE UPDATE ON modules
    FOR EACH ROW EXECUTE FUNCTION set_last_updated();

-- Request changes
DROP TRIGGER IF EXISTS trg_request_changes_last_updated ON request_changes;
CREATE TRIGGER trg_request_changes_last_updated
    BEFORE UPDATE ON request_changes
    FOR EACH ROW EXECUTE FUNCTION set_last_updated();


-- ============================================================
-- STORED FUNCTIONS
-- ============================================================

-- ── calc_readiness(student_id) → readiness record ────────────
CREATE OR REPLACE FUNCTION calc_readiness(p_student_id UUID)
RETURNS TABLE (
    subject_name    TEXT,
    pre_score       NUMERIC,
    current_score   NUMERIC,
    subject_avg     NUMERIC
) LANGUAGE sql STABLE AS $$
    SELECT
        s.name                                              AS subject_name,
        COALESCE(MAX(CASE WHEN a.type = 'PRE_ASSESSMENT' THEN sub.score END), 0)  AS pre_score,
        COALESCE(MAX(CASE WHEN a.type = 'POST_ASSESSMENT' THEN sub.score END), 0) AS current_score,
        COALESCE(AVG(sub.score), 0)                         AS subject_avg
    FROM assessment_submissions sub
    JOIN assessments a  ON a.id  = sub.assessment_id
    JOIN subjects    s  ON s.id  = a.subject_id
    WHERE sub.student_id = p_student_id
    GROUP BY s.name;
$$;


-- ── overall_readiness_level(avg_score) → 'HIGH'/'MODERATE'/'LOW' ──
CREATE OR REPLACE FUNCTION overall_readiness_level(p_avg NUMERIC)
RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN p_avg >= 80 THEN 'HIGH'
        WHEN p_avg >= 65 THEN 'MODERATE'
        ELSE                  'LOW'
    END;
$$;


-- ── student_streak(student_id) → consecutive days ────────────
CREATE OR REPLACE FUNCTION student_streak(p_student_id UUID)
RETURNS INT LANGUAGE plpgsql STABLE AS $$
DECLARE
    streak    INT  := 0;
    expected  DATE := CURRENT_DATE;
    rec       RECORD;
BEGIN
    FOR rec IN
        SELECT DISTINCT submitted_at::DATE AS day
        FROM assessment_submissions
        WHERE student_id = p_student_id
        ORDER BY day DESC
    LOOP
        IF rec.day = expected THEN
            streak   := streak + 1;
            expected := expected - 1;
        ELSIF rec.day < expected THEN
            EXIT;
        END IF;
    END LOOP;
    RETURN streak;
END;
$$;


-- ── pending_approval_count() → total pending items ───────────
CREATE OR REPLACE FUNCTION pending_approval_count()
RETURNS INT LANGUAGE sql STABLE AS $$
    SELECT (
        (SELECT COUNT(*) FROM content_modules WHERE status IN ('PENDING','REMOVAL_PENDING')) +
        (SELECT COUNT(*) FROM assessments       WHERE status = 'PENDING') +
        (SELECT COUNT(*) FROM users             WHERE status = 'PENDING')
    )::INT;
$$;


-- ============================================================
-- VIEWS
-- ============================================================

-- ── v_dashboard_overview  (admin dashboard quick stats) ──────
CREATE OR REPLACE VIEW v_dashboard_overview AS
SELECT
    (SELECT COUNT(*) FROM users u JOIN roles r ON u.role_id = r.id WHERE r.name = 'STUDENT')              AS total_students,
    (SELECT COUNT(*) FROM users u JOIN roles r ON u.role_id = r.id WHERE r.name = 'FACULTY')              AS total_faculty,
    (SELECT COUNT(*) FROM subjects)                                                                         AS total_subjects,
    (SELECT COUNT(*) FROM topics)                                                                           AS total_topics,
    (SELECT COUNT(*) FROM content_modules)                                                                  AS total_content,
    (SELECT COUNT(*) FROM content_modules WHERE status IN ('PENDING','REMOVAL_PENDING'))                    AS pending_content,
    (SELECT COUNT(*) FROM assessments WHERE status = 'PENDING')                                             AS pending_assessments,
    (SELECT COUNT(*) FROM users WHERE status = 'PENDING')                                                   AS pending_users,
    (SELECT COALESCE(AVG(score),0) FROM assessment_submissions)                                             AS readiness_avg,
    pending_approval_count()                                                                                AS total_pending,
    (SELECT maintenance_mode FROM system_settings LIMIT 1)                                                  AS maintenance_mode;


-- ── v_student_summary  (per-student analytics list) ──────────
CREATE OR REPLACE VIEW v_student_summary AS
SELECT
    u.id,
    u.first_name || ' ' || u.last_name          AS name,
    u.email,
    u.institutional_id,
    u.department,
    u.status,
    COALESCE(AVG(sub.score), 0)                  AS overall_average,
    COUNT(sub.id)                                AS assessments_taken,
    overall_readiness_level(COALESCE(AVG(sub.score), 0)) AS readiness_probability
FROM users u
JOIN roles r ON u.role_id = r.id
LEFT JOIN assessment_submissions sub ON sub.student_id = u.id
WHERE r.name = 'STUDENT'
GROUP BY u.id, u.first_name, u.last_name, u.email, u.institutional_id, u.department, u.status;


-- ── v_assessment_with_meta  (assessments + joined names) ──────
CREATE OR REPLACE VIEW v_assessment_with_meta AS
SELECT
    a.*,
    s.name                                        AS subject_name,
    t.title                                       AS topic_title,
    u.first_name || ' ' || u.last_name            AS author_name
FROM assessments a
LEFT JOIN subjects s ON s.id = a.subject_id
LEFT JOIN topics   t ON t.id = a.topic_id
LEFT JOIN users    u ON u.id = a.author_id;


-- ── v_content_with_meta  (content modules + joined names) ─────
CREATE OR REPLACE VIEW v_content_with_meta AS
SELECT
    cm.*,
    s.name                                        AS subject_name,
    t.title                                       AS topic_title,
    u.first_name || ' ' || u.last_name            AS author_name_resolved
FROM content_modules cm
LEFT JOIN subjects s ON s.id = cm.subject_id
LEFT JOIN topics   t ON t.id = cm.topic_id
LEFT JOIN users    u ON u.id = cm.author_id;


-- ── v_verification_summary  (pending counts per category) ─────
CREATE OR REPLACE VIEW v_verification_summary AS
SELECT
    (SELECT COUNT(*) FROM request_changes WHERE status = 'PENDING')                      AS total_pending,
    (SELECT COUNT(*) FROM request_changes WHERE status = 'PENDING' AND category = 'SUBJECT')    AS pending_subjects,
    (SELECT COUNT(*) FROM request_changes WHERE status = 'PENDING' AND category = 'MODULE')     AS pending_modules,
    (SELECT COUNT(*) FROM request_changes WHERE status = 'PENDING' AND category = 'ASSESSMENT') AS pending_assessments,
    (SELECT COUNT(*) FROM request_changes WHERE status = 'PENDING' AND category = 'QUESTION')   AS pending_questions;


-- ── v_review_detail  (request changes with revision info) ─────
CREATE OR REPLACE VIEW v_review_detail AS
SELECT
    rc.id                                         AS request_id,
    rc.author_id                                  AS requester_id,
    u.first_name || ' ' || u.last_name            AS requested_by,
    rc.type                                       AS change_type,
    rc.category,
    rc.status                                     AS request_status,
    rc.changes_summary,
    rc.date_created,
    rc.last_updated,
    rc.revision_id,
    rev.status                                    AS revision_status,
    rev.note                                      AS revision_note,
    rev.author_id                                 AS reviewer_id
FROM request_changes rc
LEFT JOIN users     u   ON rc.author_id   = u.id
LEFT JOIN revisions rev ON rc.revision_id = rev.id;


-- ── v_whitelist_with_user  (whitelist + user account status) ──
CREATE OR REPLACE VIEW v_whitelist_with_user AS
SELECT
    w.*,
    w.first_name || ' ' || w.last_name            AS full_name,
    u.id                                          AS user_id,
    u.status                                      AS user_status
FROM whitelist w
LEFT JOIN users u ON LOWER(u.email) = LOWER(w.email);


-- ── v_subject_stats  (subjects with topic & content counts) ───
CREATE OR REPLACE VIEW v_subject_stats AS
SELECT
    s.id,
    s.name,
    s.description,
    s.color,
    s.status,
    s.created_at,
    s.updated_at,
    u.first_name || ' ' || u.last_name             AS created_by_name,
    (SELECT COUNT(*) FROM topics          WHERE subject_id = s.id)              AS topic_count,
    (SELECT COUNT(*) FROM content_modules WHERE subject_id = s.id AND status = 'APPROVED') AS approved_content_count,
    (SELECT COUNT(*) FROM assessments     WHERE subject_id = s.id AND status = 'APPROVED') AS approved_assessment_count
FROM subjects s
LEFT JOIN users u ON u.id = s.created_by;


-- ── v_activity_feed  (recent activity with user names) ────────
CREATE OR REPLACE VIEW v_activity_feed AS
SELECT
    al.id,
    al.action,
    al.target,
    al.target_id,
    al.ip_address,
    al.created_at,
    al.user_id,
    u.first_name || ' ' || u.last_name             AS user_name,
    r.name                                         AS user_role
FROM activity_logs al
LEFT JOIN users u ON u.id = al.user_id
LEFT JOIN roles r ON r.id = u.role_id;