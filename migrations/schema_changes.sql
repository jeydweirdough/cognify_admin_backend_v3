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
    cvsu_id 		 VARCHAR(100),
	first_name       VARCHAR(100) NOT NULL,
    middle_name      VARCHAR(100),
    last_name        VARCHAR(100) NOT NULL,
    email            VARCHAR(255) NOT NULL UNIQUE,
    password         VARCHAR(255) NOT NULL,
    role_id          UUID         NOT NULL REFERENCES roles(id),
    status           VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING','ACTIVE','REGISTERED','REMOVED')),
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
    format      VARCHAR(10)  NOT NULL DEFAULT 'TEXT' CHECK (format IN ('TEXT', 'PDF')), -- NEW
    file_url    TEXT,                                                                   -- NEW
    file_name   VARCHAR(255),                                                           -- NEW
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
                CHECK (type IN ('PRE_ASSESSMENT','QUIZ','POST_ASSESSMENT')),
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
    rc.id AS request_id,
    rc.type AS entity_type,
    rc.target_id AS entity_id,
    rc.created_by AS requested_by,
    rc.revisions_list,
    
    -- 1. The Proposed Changes (Already JSONB)
    rc.content AS proposed_data,
    
    -- 2. The Original Data (Dynamically converted to JSONB based on the type)
    CASE 
        WHEN rc.type = 'SUBJECT' THEN to_jsonb(s.*)
        WHEN rc.type = 'MODULE' THEN to_jsonb(m.*)
        WHEN rc.type = 'ASSESSMENT' THEN to_jsonb(a.*)
        ELSE NULL
    END AS original_data

FROM 
    request_changes rc
-- 3. Left Join all possible tables. 
-- The "ON" clause ensures it only joins if the TYPE and ID both match.
LEFT JOIN subjects s    ON rc.type = 'SUBJECT'    AND rc.target_id = s.id
LEFT JOIN modules m     ON rc.type = 'MODULE'     AND rc.target_id = m.id
LEFT JOIN assessments a ON rc.type = 'ASSESSMENT' AND rc.target_id = a.id;

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

AUTH function
1. Create the Login Function
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
        AND u.status = 'ACTIVE'; -- Prevent pending/removed users from logging in
END;
$$ LANGUAGE plpgsql;