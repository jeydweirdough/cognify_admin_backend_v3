-- SCHEMA

-- ================================================================
-- FULL SCHEMA — DROP, RECREATE, VIEWS
-- Run this file to start completely clean.
-- ================================================================


-- ================================================================
-- SECTION 1: TEARDOWN
-- Drop views first (they depend on tables), then tables in reverse
-- dependency order, then extensions.
-- ================================================================

DROP VIEW IF EXISTS v_assessment_detail      CASCADE;
DROP VIEW IF EXISTS v_assessments_list       CASCADE;
DROP VIEW IF EXISTS v_subject_overview       CASCADE;
DROP VIEW IF EXISTS v_subjects_list          CASCADE;
DROP VIEW IF EXISTS v_review_detail          CASCADE;
DROP VIEW IF EXISTS v_verification_summary   CASCADE;
DROP VIEW IF EXISTS v_verification_queue     CASCADE;
DROP VIEW IF EXISTS v_dashboard_overview     CASCADE;
DROP VIEW IF EXISTS v_registered_users       CASCADE;

DROP TABLE IF EXISTS assessment_results  CASCADE;
DROP TABLE IF EXISTS assessment_questions CASCADE;
DROP TABLE IF EXISTS revision_items      CASCADE;
DROP TABLE IF EXISTS request_changes     CASCADE;
DROP TABLE IF EXISTS revisions           CASCADE;
DROP TABLE IF EXISTS assessments         CASCADE;
DROP TABLE IF EXISTS questions           CASCADE;
DROP TABLE IF EXISTS modules             CASCADE;
DROP TABLE IF EXISTS enrollments         CASCADE;
DROP TABLE IF EXISTS subjects            CASCADE;
DROP TABLE IF EXISTS users               CASCADE;
DROP TABLE IF EXISTS roles               CASCADE;
DROP TABLE IF EXISTS system_settings     CASCADE;

DROP FUNCTION IF EXISTS update_last_updated_column CASCADE;


-- ================================================================
-- SECTION 2: EXTENSIONS
-- ================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- ================================================================
-- SECTION 3: TABLES
-- ================================================================

-- ----------------
-- ROLES
-- ----------------
CREATE TABLE roles (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(50) NOT NULL,       -- 'STUDENT' | 'FACULTY' | 'ADMIN'
    permissions JSONB,
    is_system   BOOLEAN DEFAULT FALSE
);

-- ----------------
-- USERS
-- ----------------
CREATE TABLE users (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name   VARCHAR(255),
    middle_name  VARCHAR(255),
    last_name    VARCHAR(255),
    email        VARCHAR(255) UNIQUE,
    password     VARCHAR(255),                  -- hashed password
    department   VARCHAR(255),
    role_id      UUID REFERENCES roles(id),
    status       VARCHAR(50) DEFAULT 'PENDING', -- PENDING | ACTIVE | DEACTIVATED
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login   TIMESTAMP                      -- NULL until first login
);

-- ----------------
-- SYSTEM SETTINGS
-- Single-row config table
-- ----------------
CREATE TABLE system_settings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    academic_year       VARCHAR(255),
    institutional_name  VARCHAR(255),
    maintenance_mode    BOOLEAN DEFAULT FALSE
);

-- ----------------
-- SUBJECTS
-- ----------------
CREATE TABLE subjects (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(255),
    description  TEXT,
    color        VARCHAR(255),
    status       VARCHAR(50),               -- DRAFT | PUBLISHED | ARCHIVED
    weight       INT DEFAULT 0,               -- percentage weight e.g. 20, 40
    passing_rate INT,
    author_id    UUID REFERENCES users(id),
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------
-- ENROLLMENTS
-- Tracks which students are enrolled in which subjects
-- ----------------
CREATE TABLE enrollments (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id    UUID REFERENCES users(id) ON DELETE CASCADE,
    subject_id    UUID REFERENCES subjects(id) ON DELETE CASCADE,
    status        VARCHAR(50) DEFAULT 'ACTIVE',
    date_enrolled TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, subject_id)
);

-- ----------------
-- MODULES
-- Belongs to a subject. Supports sub-modules via parent_id.
-- ----------------
CREATE TABLE modules (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id   UUID REFERENCES subjects(id) ON DELETE CASCADE,
    parent_id    UUID REFERENCES modules(id),
    author_id    UUID REFERENCES users(id),
    title        VARCHAR(255),
    file_name    VARCHAR(255),
    file_url     VARCHAR(255),
    content      TEXT,
    format       VARCHAR(255),
    status       VARCHAR(50),
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------
-- QUESTIONS
-- Standalone question bank; linked to assessments via junction table
-- ----------------
CREATE TABLE questions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id      UUID REFERENCES users(id),
    text           TEXT,
    options        JSONB,                   -- array of answer option strings
    correct_answer INT,                     -- index into options array
    date_created   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------
-- ASSESSMENTS
-- type: PRE_ASSESSMENT | POST_ASSESSMENT | QUIZ | EXAM | ACTIVITY
-- items: declared number of questions (may differ from actual count)
-- ----------------
CREATE TABLE assessments (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id   UUID REFERENCES subjects(id),
    author_id    UUID REFERENCES users(id),
    title        VARCHAR(255),
    type         VARCHAR(50),
    items        INT,
    time_limit   INT,                       -- in minutes
    schedule     TIMESTAMP,
    status       VARCHAR(50),
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Assessment ↔ Question (many-to-many)
CREATE TABLE assessment_questions (
    assessment_id UUID REFERENCES assessments(id) ON DELETE CASCADE,
    question_id   UUID REFERENCES questions(id)   ON DELETE CASCADE,
    PRIMARY KEY (assessment_id, question_id)
);

-- ----------------
-- ASSESSMENT RESULTS
-- One row per attempt per student
-- ----------------
CREATE TABLE assessment_results (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id  UUID REFERENCES assessments(id),
    student_id     UUID REFERENCES users(id),
    score          INT,
    out_of         INT,
    attempt_number INT,
    date_taken     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------
-- REVISIONS
-- A revision is a review record attached to a request_change.
-- author_id = the reviewer who wrote the revision note.
-- ----------------
CREATE TABLE revisions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id    UUID REFERENCES users(id),
    note         TEXT,
    status       VARCHAR(50),               -- PENDING | APPROVED | REJECTED
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Polymorphic: one revision can reference multiple item types
CREATE TABLE revision_items (
    revision_id UUID REFERENCES revisions(id) ON DELETE CASCADE,
    item_type   VARCHAR(50) NOT NULL,       -- 'assessment' | 'question' | 'module' | 'subject'
    item_id     UUID NOT NULL,
    PRIMARY KEY (revision_id, item_type, item_id)
);

-- ----------------
-- REQUEST CHANGES
-- A change request submitted by a faculty/author for admin review.
--
-- changes_summary (JSONB) MUST follow this structure:
--   {
--     "target_id": "<uuid of the item being changed>",
--     "changes": [
--       { "field": "title", "old_value": "...", "new_value": "..." }
--     ]
--   }
--
-- type:     ADD | UPDATE | REMOVE
-- category: SUBJECT | MODULE | ASSESSMENT | QUESTION
--
-- QUESTION category = updating questions on an assessment (treated
-- as an assessment UPDATE in verification views).
-- ----------------
CREATE TABLE request_changes (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id        UUID REFERENCES users(id),
    revision_id      UUID REFERENCES revisions(id),
    changes_summary  JSONB,
    type             VARCHAR(50),
    category         VARCHAR(50),
    status           VARCHAR(50),           -- PENDING | APPROVED | REJECTED
    date_created     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ================================================================
-- SECTION 4: TRIGGER — auto-update last_updated
-- ================================================================

CREATE OR REPLACE FUNCTION update_last_updated_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE tbl TEXT;
BEGIN
    FOR tbl IN
        SELECT unnest(ARRAY[
            'users','subjects','modules','questions',
            'assessments','revisions','request_changes'
        ])
    LOOP
        EXECUTE format(
            'CREATE TRIGGER %I_last_updated
             BEFORE UPDATE ON %I
             FOR EACH ROW EXECUTE FUNCTION update_last_updated_column();',
            tbl, tbl
        );
    END LOOP;
END$$;


-- ================================================================
-- SECTION 5: VIEWS
-- ================================================================

-- ----------------------------------------------------------------
-- VIEW: v_dashboard_overview
-- Single-row summary for the main dashboard.
-- Includes: subject/module counts, maintenance flag, enrolled
-- students, pending revisions, user distribution, monthly growth.
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW v_dashboard_overview AS
WITH
subject_stats AS (
    SELECT COUNT(*) AS total_subjects
    FROM subjects
    WHERE status IS DISTINCT FROM 'ARCHIVED'
),
module_stats AS (
    SELECT COUNT(*) AS total_modules
    FROM modules
    WHERE status IS DISTINCT FROM 'ARCHIVED'
),
maintenance AS (
    SELECT COALESCE(
        (SELECT maintenance_mode FROM system_settings LIMIT 1),
        FALSE
    ) AS is_maintenance
),
enrolled_students AS (
    SELECT COUNT(DISTINCT e.student_id) AS total_enrolled
    FROM enrollments e
    JOIN users u ON u.id = e.student_id
    JOIN roles r ON u.role_id = r.id
    WHERE u.status = 'ACTIVE'
      AND e.status = 'ACTIVE'
      AND r.name = 'STUDENT'
),
pending_revisions AS (
    SELECT COUNT(*) AS total_pending
    FROM revisions
    WHERE status = 'PENDING'
),
user_dist AS (
    SELECT
        COUNT(*) FILTER (WHERE r.name = 'STUDENT') AS total_students,
        COUNT(*) FILTER (WHERE r.name = 'FACULTY') AS total_faculty,
        COUNT(*) FILTER (WHERE r.name = 'ADMIN')   AS total_admins,
        COUNT(*)                                         AS total_users
    FROM users u
    LEFT JOIN roles r ON u.role_id = r.id
    WHERE u.status != 'DEACTIVATED'
),
user_growth AS (
    SELECT JSON_AGG(g ORDER BY (g->>'month')) AS growth
    FROM (
        SELECT JSON_BUILD_OBJECT(
            'month',        TO_CHAR(DATE_TRUNC('month', u.date_created), 'YYYY-MM'),
            'new_users',    COUNT(*),
            'new_students', COUNT(*) FILTER (WHERE r.name = 'STUDENT'),
            'new_faculty',  COUNT(*) FILTER (WHERE r.name = 'FACULTY'),
            'new_admins',   COUNT(*) FILTER (WHERE r.name = 'ADMIN')
        ) AS g
        FROM users u
        LEFT JOIN roles r ON u.role_id = r.id
        WHERE u.date_created >= NOW() - INTERVAL '12 months'
        GROUP BY DATE_TRUNC('month', u.date_created)
    ) sub
)
SELECT
    ss.total_subjects,
    ms.total_modules,
    m.is_maintenance,
    es.total_enrolled         AS enrolled_students,
    pr.total_pending          AS pending_revisions,
    ud.total_students,
    ud.total_faculty,
    ud.total_admins,
    ud.total_users,
    ug.growth                 AS user_growth_by_month
FROM subject_stats ss
CROSS JOIN module_stats ms
CROSS JOIN maintenance m
CROSS JOIN enrolled_students es
CROSS JOIN pending_revisions pr
CROSS JOIN user_dist ud
CROSS JOIN user_growth ug;


-- ----------------------------------------------------------------
-- VIEW: v_registered_users
-- All non-pending users with role info and activity summary.
-- For pending/whitelist users: SELECT * FROM users WHERE status = 'PENDING'
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW v_registered_users AS
SELECT
    u.id                                         AS user_id,
    u.first_name,
    u.middle_name,
    u.last_name,
    CONCAT(u.first_name, ' ', u.last_name)       AS full_name,
    u.email,
    u.department,
    u.status,
    r.id                                         AS role_id,
    r.name                                       AS role_name,
    u.date_created                               AS date_registered,
    u.last_login,
    u.last_updated,
    COUNT(DISTINCT ar.id)                        AS total_assessments_taken,
    MAX(ar.date_taken)                           AS last_assessment_date
FROM users u
LEFT JOIN roles r               ON u.role_id = r.id
LEFT JOIN assessment_results ar ON ar.student_id = u.id
WHERE u.status != 'PENDING'
GROUP BY
    u.id, u.first_name, u.middle_name, u.last_name,
    u.email, u.department, u.status,
    u.date_created, u.last_login, u.last_updated,
    r.id, r.name;


-- ----------------------------------------------------------------
-- VIEW: v_subjects_list
-- One row per subject with weighted score and passing stats.
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW v_subjects_list AS
SELECT
    s.id                                         AS subject_id,
    s.name,
    s.description,
    s.color,
    s.status,
    s.weight,
    s.passing_rate,
    CONCAT(u.first_name, ' ', u.last_name)       AS author_name,
    s.author_id,
    s.date_created,
    s.last_updated,
    ROUND(
        AVG(ar.score::DECIMAL / NULLIF(ar.out_of, 0) * 100), 2
    )                                            AS weighted_score,
    COUNT(*) FILTER (
        WHERE (ar.score::DECIMAL / NULLIF(ar.out_of, 0) * 100) >= s.passing_rate
    )                                            AS students_passing,
    COUNT(DISTINCT ar.student_id)                AS students_attempted
FROM subjects s
LEFT JOIN users u               ON s.author_id = u.id
LEFT JOIN assessments a         ON a.subject_id = s.id
LEFT JOIN assessment_results ar ON ar.assessment_id = a.id
GROUP BY
    s.id, s.name, s.description, s.color, s.status,
    s.weight, s.passing_rate, s.author_id, s.date_created, s.last_updated,
    u.first_name, u.last_name;


-- ----------------------------------------------------------------
-- VIEW: v_subject_overview
-- Full subject detail: info + modules as JSON.
-- Filter: SELECT * FROM v_subject_overview WHERE subject_id = '<uuid>';
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW v_subject_overview AS
SELECT
    s.id                                         AS subject_id,
    s.name                                       AS subject_name,
    s.description,
    s.color,
    s.status,
    s.weight,
    s.passing_rate,
    s.author_id,
    CONCAT(au.first_name, ' ', au.last_name)     AS author_name,
    s.date_created,
    s.last_updated,
    COUNT(DISTINCT a.id)                         AS total_assessments,
    COUNT(DISTINCT e.student_id)                 AS enrolled_students,
    ROUND(
        AVG(ar.score::DECIMAL / NULLIF(ar.out_of, 0) * 100), 2
    )                                            AS average_score_pct,
    -- All modules (flat list with parent_id for tree reconstruction client-side)
    (
        SELECT JSON_AGG(
            JSON_BUILD_OBJECT(
                'module_id',    m.id,
                'title',        m.title,
                'format',       m.format,
                'status',       m.status,
                'file_name',    m.file_name,
                'file_url',     m.file_url,
                'parent_id',    m.parent_id,
                'author_id',    m.author_id,
                'date_created', m.date_created,
                'last_updated', m.last_updated
            ) ORDER BY m.date_created
        )
        FROM modules m WHERE m.subject_id = s.id
    )                                            AS modules,
    (SELECT COUNT(*) FROM modules m WHERE m.subject_id = s.id AND m.parent_id IS NULL) AS top_level_modules,
    (SELECT COUNT(*) FROM modules m WHERE m.subject_id = s.id)                         AS total_modules
FROM subjects s
LEFT JOIN users au              ON s.author_id = au.id
LEFT JOIN assessments a         ON a.subject_id = s.id
LEFT JOIN enrollments e         ON e.subject_id = s.id AND e.status = 'ACTIVE'
LEFT JOIN assessment_results ar ON ar.assessment_id = a.id
GROUP BY
    s.id, s.name, s.description, s.color, s.status,
    s.weight, s.passing_rate, s.author_id, s.date_created, s.last_updated,
    au.first_name, au.last_name;


-- ----------------------------------------------------------------
-- VIEW: v_assessments_list
-- One row per assessment with question count and result stats.
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW v_assessments_list AS
SELECT
    a.id                                         AS assessment_id,
    a.title,
    a.type,
    a.items                                      AS declared_items,
    COUNT(DISTINCT aq.question_id)               AS actual_question_count,
    a.time_limit,
    a.schedule,
    a.status,
    a.author_id,
    CONCAT(u.first_name, ' ', u.last_name)       AS author_name,
    s.id                                         AS subject_id,
    s.name                                       AS subject_name,
    a.date_created,
    a.last_updated,
    COUNT(DISTINCT ar.student_id)                AS students_attempted,
    ROUND(
        AVG(ar.score::DECIMAL / NULLIF(ar.out_of, 0) * 100), 2
    )                                            AS average_score_pct
FROM assessments a
LEFT JOIN subjects s              ON a.subject_id = s.id
LEFT JOIN users u                 ON a.author_id = u.id
LEFT JOIN assessment_questions aq ON aq.assessment_id = a.id
LEFT JOIN assessment_results ar   ON ar.assessment_id = a.id
GROUP BY
    a.id, a.title, a.type, a.items, a.time_limit,
    a.schedule, a.status, a.author_id, a.date_created, a.last_updated,
    s.id, s.name, u.first_name, u.last_name;


-- ----------------------------------------------------------------
-- VIEW: v_assessment_detail
-- Full assessment: all fields + questions + per-student results.
-- Filter: SELECT * FROM v_assessment_detail WHERE assessment_id = '<uuid>';
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW v_assessment_detail AS
SELECT
    a.id                                         AS assessment_id,
    a.title,
    a.type,
    a.items                                      AS declared_items,
    COUNT(DISTINCT aq.question_id)               AS actual_question_count,
    a.time_limit,
    a.schedule,
    a.status,
    a.author_id,
    CONCAT(u.first_name, ' ', u.last_name)       AS author_name,
    s.id                                         AS subject_id,
    s.name                                       AS subject_name,
    s.passing_rate                               AS subject_passing_rate,
    a.date_created,
    a.last_updated,
    -- Questions
    (
        SELECT JSON_AGG(
            JSON_BUILD_OBJECT(
                'question_id',    q.id,
                'author_id',      q.author_id,
                'text',           q.text,
                'options',        q.options,
                'correct_answer', q.correct_answer,
                'date_created',   q.date_created,
                'last_updated',   q.last_updated
            ) ORDER BY q.date_created
        )
        FROM assessment_questions aq2
        JOIN questions q ON q.id = aq2.question_id
        WHERE aq2.assessment_id = a.id
    )                                            AS questions,
    -- Result stats
    COUNT(DISTINCT ar.student_id)                AS students_attempted,
    COUNT(ar.id)                                 AS total_attempts,
    ROUND(AVG(ar.score::DECIMAL / NULLIF(ar.out_of, 0) * 100), 2) AS average_score_pct,
    ROUND(MAX(ar.score::DECIMAL / NULLIF(ar.out_of, 0) * 100), 2) AS highest_score_pct,
    ROUND(MIN(ar.score::DECIMAL / NULLIF(ar.out_of, 0) * 100), 2) AS lowest_score_pct,
    -- Per-student latest attempt
    (
        SELECT JSON_AGG(
            JSON_BUILD_OBJECT(
                'student_id',     latest.student_id,
                'student_name',   CONCAT(su.first_name, ' ', su.last_name),
                'score',          latest.score,
                'out_of',         latest.out_of,
                'score_pct',      ROUND(latest.score::DECIMAL / NULLIF(latest.out_of, 0) * 100, 2),
                'attempt_number', latest.attempt_number,
                'date_taken',     latest.date_taken
            ) ORDER BY latest.date_taken DESC
        )
        FROM (
            SELECT DISTINCT ON (student_id)
                id, student_id, score, out_of, attempt_number, date_taken
            FROM assessment_results
            WHERE assessment_id = a.id
            ORDER BY student_id, attempt_number DESC
        ) latest
        JOIN users su ON su.id = latest.student_id
    )                                            AS student_results
FROM assessments a
LEFT JOIN subjects s              ON a.subject_id = s.id
LEFT JOIN users u                 ON a.author_id = u.id
LEFT JOIN assessment_questions aq ON aq.assessment_id = a.id
LEFT JOIN assessment_results ar   ON ar.assessment_id = a.id
GROUP BY
    a.id, a.title, a.type, a.items, a.time_limit,
    a.schedule, a.status, a.author_id, a.date_created, a.last_updated,
    s.id, s.name, s.passing_rate, u.first_name, u.last_name;


-- ----------------------------------------------------------------
-- VIEW: v_verification_summary
-- Header badge counts for the verification inbox.
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW v_verification_summary AS
SELECT
    COUNT(*) FILTER (WHERE category = 'SUBJECT')    AS pending_subjects,
    COUNT(*) FILTER (WHERE category = 'MODULE')     AS pending_modules,
    COUNT(*) FILTER (WHERE category = 'ASSESSMENT') AS pending_assessments,
    COUNT(*) FILTER (WHERE category = 'QUESTION')   AS pending_question_updates,
    COUNT(*)                                         AS total_pending
FROM request_changes
WHERE status = 'PENDING';


-- ----------------------------------------------------------------
-- VIEW: v_verification_queue
-- All pending request_changes across all categories.
-- QUESTION rows are surfaced as ASSESSMENT/UPDATE per business logic.
-- Excludes changes_summary (that's for the review detail view).
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW v_verification_queue AS

SELECT
    rc.id                                        AS request_id,
    rc.author_id,
    CONCAT(u.first_name, ' ', u.last_name)       AS requested_by,
    rc.type                                      AS change_type,
    rc.category,
    rc.status                                    AS request_status,
    rc.date_created,
    rc.last_updated,
    rc.revision_id,
    rev.status                                   AS revision_status,
    rev.note                                     AS revision_note,
    s.id                                         AS item_id,
    s.name                                       AS item_title,
    s.status                                     AS item_current_status
FROM request_changes rc
LEFT JOIN users u       ON rc.author_id = u.id
LEFT JOIN revisions rev ON rc.revision_id = rev.id
LEFT JOIN subjects s    ON s.id = (rc.changes_summary->>'target_id')::UUID
WHERE rc.category = 'SUBJECT'

UNION ALL

SELECT
    rc.id,
    rc.author_id,
    CONCAT(u.first_name, ' ', u.last_name),
    rc.type,
    rc.category,
    rc.status,
    rc.date_created,
    rc.last_updated,
    rc.revision_id,
    rev.status,
    rev.note,
    mo.id,
    mo.title,
    mo.status
FROM request_changes rc
LEFT JOIN users u       ON rc.author_id = u.id
LEFT JOIN revisions rev ON rc.revision_id = rev.id
LEFT JOIN modules mo    ON mo.id = (rc.changes_summary->>'target_id')::UUID
WHERE rc.category = 'MODULE'

UNION ALL

SELECT
    rc.id,
    rc.author_id,
    CONCAT(u.first_name, ' ', u.last_name),
    rc.type,
    'ASSESSMENT',                                -- category
    rc.status,
    rc.date_created,
    rc.last_updated,
    rc.revision_id,
    rev.status,
    rev.note,
    a.id,
    a.title,
    a.status
FROM request_changes rc
LEFT JOIN users u       ON rc.author_id = u.id
LEFT JOIN revisions rev ON rc.revision_id = rev.id
LEFT JOIN assessments a ON a.id = (rc.changes_summary->>'target_id')::UUID
WHERE rc.category = 'ASSESSMENT'

UNION ALL

-- QUESTION changes surface as ASSESSMENT / UPDATE
SELECT
    rc.id,
    rc.author_id,
    CONCAT(u.first_name, ' ', u.last_name),
    'UPDATE',                                    -- change_type always UPDATE for questions
    'ASSESSMENT',                                -- surfaced under ASSESSMENT category
    rc.status,
    rc.date_created,
    rc.last_updated,
    rc.revision_id,
    rev.status,
    rev.note,
    q.id,
    LEFT(q.text, 120)                            AS item_title,
    NULL                                         AS item_current_status
FROM request_changes rc
LEFT JOIN users u       ON rc.author_id = u.id
LEFT JOIN revisions rev ON rc.revision_id = rev.id
LEFT JOIN questions q   ON q.id = (rc.changes_summary->>'target_id')::UUID
WHERE rc.category = 'QUESTION';


-- ----------------------------------------------------------------
-- VIEW: v_review_detail
-- Full review panel for a single request_change.
-- Shows current live state of the item, proposed changes, and
-- any revision notes with author info.
-- Filter: SELECT * FROM v_review_detail WHERE request_id = '<uuid>';
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW v_review_detail AS

-- ASSESSMENT (includes questions)
SELECT
    rc.id                                        AS request_id,
    rc.category,
    rc.type                                      AS change_type,
    rc.status                                    AS request_status,
    rc.author_id                                 AS requester_id,
    CONCAT(ru.first_name, ' ', ru.last_name)     AS requester_name,
    rc.date_created                              AS request_date,
    rc.changes_summary                           AS proposed_changes,
    -- Current live state
    a.id                                         AS current_item_id,
    a.title                                      AS current_title,
    a.type                                       AS current_type,
    a.items                                      AS current_items,
    a.time_limit                                 AS current_time_limit,
    a.schedule                                   AS current_schedule,
    a.status                                     AS current_status,
    a.date_created                               AS current_date_created,
    a.last_updated                               AS current_last_updated,
    -- Current questions
    (
        SELECT JSON_AGG(JSON_BUILD_OBJECT(
            'question_id',    q.id,
            'text',           q.text,
            'options',        q.options,
            'correct_answer', q.correct_answer
        ))
        FROM assessment_questions aq
        JOIN questions q ON q.id = aq.question_id
        WHERE aq.assessment_id = a.id
    )                                            AS current_content,
    -- Revision
    rev.id                                       AS revision_id,
    rev.status                                   AS revision_status,
    rev.note                                     AS revision_note,
    rev.date_created                             AS revision_date,
    rev.author_id                                AS revision_author_id,
    CONCAT(rau.first_name, ' ', rau.last_name)   AS revision_author_name,
    (
        SELECT JSON_AGG(JSON_BUILD_OBJECT('item_type', ri.item_type, 'item_id', ri.item_id))
        FROM revision_items ri WHERE ri.revision_id = rev.id
    )                                            AS revision_items
FROM request_changes rc
LEFT JOIN users ru      ON rc.author_id = ru.id
LEFT JOIN assessments a ON a.id = (rc.changes_summary->>'target_id')::UUID
LEFT JOIN revisions rev ON rc.revision_id = rev.id
LEFT JOIN users rau     ON rev.author_id = rau.id
WHERE rc.category IN ('ASSESSMENT', 'QUESTION')

UNION ALL

-- SUBJECT
SELECT
    rc.id, rc.category, rc.type, rc.status,
    rc.author_id,
    CONCAT(ru.first_name, ' ', ru.last_name),
    rc.date_created,
    rc.changes_summary,
    s.id, s.name, NULL, NULL, NULL, NULL,
    s.status, s.date_created, s.last_updated,
    (
        SELECT JSON_AGG(JSON_BUILD_OBJECT(
            'module_id', m.id, 'title', m.title,
            'format', m.format, 'status', m.status
        ))
        FROM modules m WHERE m.subject_id = s.id
    ),
    rev.id, rev.status, rev.note, rev.date_created, rev.author_id,
    CONCAT(rau.first_name, ' ', rau.last_name),
    (
        SELECT JSON_AGG(JSON_BUILD_OBJECT('item_type', ri.item_type, 'item_id', ri.item_id))
        FROM revision_items ri WHERE ri.revision_id = rev.id
    )
FROM request_changes rc
LEFT JOIN users ru      ON rc.author_id = ru.id
LEFT JOIN subjects s    ON s.id = (rc.changes_summary->>'target_id')::UUID
LEFT JOIN revisions rev ON rc.revision_id = rev.id
LEFT JOIN users rau     ON rev.author_id = rau.id
WHERE rc.category = 'SUBJECT'

UNION ALL

-- MODULE
SELECT
    rc.id, rc.category, rc.type, rc.status,
    rc.author_id,
    CONCAT(ru.first_name, ' ', ru.last_name),
    rc.date_created,
    rc.changes_summary,
    mo.id, mo.title, mo.format, NULL, NULL, NULL,
    mo.status, mo.date_created, mo.last_updated,
    (SELECT JSON_BUILD_OBJECT(
        'content', mo.content, 'file_name', mo.file_name, 'file_url', mo.file_url
    )),
    rev.id, rev.status, rev.note, rev.date_created, rev.author_id,
    CONCAT(rau.first_name, ' ', rau.last_name),
    (
        SELECT JSON_AGG(JSON_BUILD_OBJECT('item_type', ri.item_type, 'item_id', ri.item_id))
        FROM revision_items ri WHERE ri.revision_id = rev.id
    )
FROM request_changes rc
LEFT JOIN users ru      ON rc.author_id = ru.id
LEFT JOIN modules mo    ON mo.id = (rc.changes_summary->>'target_id')::UUID
LEFT JOIN revisions rev ON rc.revision_id = rev.id
LEFT JOIN users rau     ON rev.author_id = rau.id
WHERE rc.category = 'MODULE';


-- ================================================================
-- QUICK REFERENCE
-- ================================================================
--
-- VIEWS (use WHERE clause to filter):
--   v_dashboard_overview          → single row, no filter needed
--   v_registered_users            → all active/non-pending users
--   v_subjects_list               → all subjects with scores
--   v_subject_overview            → WHERE subject_id = '<uuid>'
--   v_assessments_list            → all assessments
--   v_assessment_detail           → WHERE assessment_id = '<uuid>'
--   v_verification_summary        → single row badge counts
--   v_verification_queue          → WHERE status = 'PENDING' (optional)
--   v_review_detail               → WHERE request_id = '<uuid>'
--
-- WHITELIST (pending users — no separate view needed):
--   SELECT * FROM users WHERE status = 'PENDING' ORDER BY date_created;
--
-- changes_summary JSONB contract:
--   { "target_id": "<uuid>", "changes": [{ "field": "", "old_value": "", "new_value": "" }] }
--
-- ================================================================