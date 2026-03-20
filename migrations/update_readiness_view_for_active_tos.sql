-- ============================================================
-- update_readiness_view_for_active_tos.sql
--
-- Updates view_student_individual_readiness to ONLY consider
-- subjects that are part of the currently ACTIVE TOS version.
--
-- This script also recreates dependent views (view_general_readiness,
-- view_admin_dashboard_stats) that may have been dropped by CASCADE.
-- ============================================================

-- Drop the views with CASCADE to ensure a clean slate, then recreate all.
DROP VIEW IF EXISTS view_admin_dashboard_stats         CASCADE;
DROP VIEW IF EXISTS view_general_readiness             CASCADE;
DROP VIEW IF EXISTS view_student_individual_readiness  CASCADE;

-- 1. Updated view_student_individual_readiness (Integrated with Active TOS filtering)
CREATE VIEW view_student_individual_readiness AS
WITH
active_tos AS (
    SELECT data->'subjects' AS subjects
    FROM   tos_versions
    WHERE  status = 'ACTIVE'
    LIMIT 1
),
active_subject_names AS (
    SELECT jsonb_array_elements(subjects)->>'subject' AS name
    FROM   active_tos
),
approved_subjects AS (
    SELECT s.id, s.name
    FROM   subjects s
    WHERE  s.status = 'APPROVED'
      AND  s.name IN (SELECT name FROM active_subject_names)
),
total_approved AS (
    SELECT COUNT(*) AS cnt FROM approved_subjects
),
-- Deduplicate results: keep only the LATEST attempt per assessment per user
latest_results AS (
    SELECT DISTINCT ON (ar.user_id, ar.assessment_id)
           ar.user_id,
           ar.assessment_id,
           (ar.score::NUMERIC / NULLIF(ar.total_items, 0)) * 100 AS pct,
           a.type,
           a.subject_id
    FROM   assessment_results ar
    JOIN   assessments a ON a.id = ar.assessment_id
    WHERE  a.subject_id IN (SELECT id FROM approved_subjects)
      AND  a.type <> 'PRE_ASSESSMENT'
    ORDER  BY ar.user_id, ar.assessment_id, ar.date_taken DESC
),
-- Step 1: AVG score per user × subject × assessment type (from deduped results)
type_avgs AS (
    SELECT
        user_id,
        subject_id,
        type,
        AVG(pct) AS type_avg
    FROM   latest_results
    GROUP  BY user_id, subject_id, type
),
-- Step 2: weighted score per user × subject
subject_weighted AS (
    SELECT
        user_id,
        subject_id,
        SUM(type_avg * CASE type
            WHEN 'MOCK_EXAM'          THEN 0.40
            WHEN 'FINAL_ASSESSMENT'   THEN 0.30
            WHEN 'POST_ASSESSMENT'    THEN 0.20
            WHEN 'QUIZ'               THEN 0.10
            ELSE 0
        END) AS weighted_sum,
        SUM(CASE type
            WHEN 'MOCK_EXAM'          THEN 0.40
            WHEN 'FINAL_ASSESSMENT'   THEN 0.30
            WHEN 'POST_ASSESSMENT'    THEN 0.20
            WHEN 'QUIZ'               THEN 0.10
            ELSE 0
        END) AS weight_total
    FROM   type_avgs
    GROUP  BY user_id, subject_id
),
-- Per-subject normalised score
subject_scores AS (
    SELECT
        user_id,
        subject_id,
        CASE WHEN weight_total > 0 THEN weighted_sum / weight_total ELSE 0 END AS subject_score
    FROM subject_weighted
),
-- Step 3: raw readiness = SUM(per-subject scores) / total approved (zero-fill)
raw_readiness AS (
    SELECT
        u.id AS user_id,
        ROUND(
            COALESCE(SUM(COALESCE(ss.subject_score, 0)), 0)::NUMERIC
            / NULLIF((SELECT cnt FROM total_approved), 0),
        1) AS raw_pct
    FROM       users            u
    JOIN       roles            r   ON r.id = u.role_id
    CROSS JOIN approved_subjects ap
    LEFT JOIN  subject_scores   ss  ON ss.user_id = u.id AND ss.subject_id = ap.id
    WHERE  r.name ILIKE 'student' AND u.status = 'ACTIVE'
    GROUP  BY u.id
),
-- Step 4: mock exam average per user (latest attempt per assessment)
mock_avgs AS (
    SELECT
        ar.user_id,
        AVG(pct) AS mock_avg
    FROM (
        SELECT DISTINCT ON (ar2.user_id, ar2.assessment_id)
               ar2.user_id,
               (ar2.score::NUMERIC / NULLIF(ar2.total_items, 0)) * 100 AS pct
        FROM   assessment_results ar2
        JOIN   assessments a2 ON a2.id = ar2.assessment_id
        WHERE  a2.type = 'MOCK_EXAM'
        ORDER  BY ar2.user_id, ar2.assessment_id, ar2.date_taken DESC
    ) ar
    GROUP BY ar.user_id
),
-- Progress: subjects touched vs total approved
subject_attempted AS (
    SELECT
        ar.user_id,
        COUNT(DISTINCT a.subject_id) AS subjects_attempted
    FROM  assessment_results ar
    JOIN  assessments a ON a.id = ar.assessment_id
    WHERE a.subject_id IN (SELECT id FROM approved_subjects)
      AND a.type <> 'PRE_ASSESSMENT'
    GROUP BY ar.user_id
)
SELECT
    rr.user_id,
    u.first_name,
    u.last_name,
    -- Reality-check blend with mock exam average
    ROUND(
        CASE
            WHEN ma.mock_avg IS NULL THEN
                rr.raw_pct
            WHEN ma.mock_avg < rr.raw_pct THEN
                -- Mock below computed: pull down (quiz inflation guard)
                rr.raw_pct * 0.70 + ma.mock_avg * 0.30
            ELSE
                -- Mock above computed: slight upward blend
                rr.raw_pct * 0.80 + ma.mock_avg * 0.20
        END,
    1) AS readiness_percentage,
    -- Progress percentage
    ROUND(
        COALESCE(sa.subjects_attempted, 0)::NUMERIC
        / NULLIF((SELECT cnt FROM total_approved), 0)
        * 100,
    1) AS progress_percentage
FROM       raw_readiness       rr
JOIN       users               u   ON u.id = rr.user_id
LEFT JOIN  mock_avgs           ma  ON ma.user_id = rr.user_id
LEFT JOIN  subject_attempted   sa  ON sa.user_id = rr.user_id;

-- 2. Restored dependent views
CREATE VIEW view_general_readiness AS
SELECT ROUND(AVG(readiness_percentage), 2) AS overall_system_readiness
FROM   view_student_individual_readiness
WHERE  readiness_percentage IS NOT NULL;

CREATE VIEW view_admin_dashboard_stats AS
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
