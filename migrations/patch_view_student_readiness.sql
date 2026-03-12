-- ============================================================
-- patch_view_student_readiness.sql
--
-- Fixes view_student_individual_readiness to match _calc_readiness()
-- in analytics.py exactly, so all parts of the system show the
-- same readiness percentage.
--
-- Algorithm (matches Python _calc_readiness exactly):
--   Step 1 — per student × subject × assessment type:
--             AVG((score / total_items) * 100)
--             PRE_ASSESSMENT is excluded (baseline, not a board score).
--   Step 2 — per student × subject: MAX across all non-pre types
--             (student's best attempt counts).
--   Step 3 — zero-fill: approved subjects with no results → 0.
--   Step 4 — overall = SUM(per-subject scores) / total_approved_subjects
--
-- Run this script against your live database to apply the fix.
-- Safe to re-run (CREATE OR REPLACE).
-- ============================================================

CREATE OR REPLACE VIEW view_student_individual_readiness AS
-- Computation mirrors _calc_readiness() in analytics.py exactly:
--   Step 1 — per student × subject × assessment type: AVG((score/items)*100)
--             PRE_ASSESSMENT is excluded (it's a baseline, not a board score).
--   Step 2 — per student × subject: take MAX across all non-pre assessment types.
--             This means the student's best attempt per subject is used.
--   Step 3 — zero-fill: approved subjects with no results contribute 0.
--   Step 4 — overall = SUM(per-subject scores) / total_approved_subjects
WITH
approved_subjects AS (
    SELECT id, name
    FROM   subjects
    WHERE  status = 'APPROVED'
),
total_approved AS (
    SELECT COUNT(*) AS cnt
    FROM   approved_subjects
),
-- Step 1: per student, per subject, per assessment type → average score %
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
-- Step 2: per student, per subject → best score across all non-pre types
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
    -- Zero-fill for subjects with no results; divide by total approved (not just attempted).
    ROUND(
        COALESCE(SUM(COALESCE(sb.subject_score, 0)), 0)::NUMERIC
        / NULLIF((SELECT cnt FROM total_approved), 0),
    1) AS readiness_percentage
FROM       users            u
JOIN       roles            r   ON r.id  = u.role_id
CROSS JOIN approved_subjects ap
LEFT  JOIN subject_best     sb  ON sb.user_id    = u.id
                                AND sb.subject_id = ap.id
WHERE  r.name ILIKE 'student'
  AND  u.status = 'ACTIVE'
GROUP BY u.id, u.first_name, u.last_name;
