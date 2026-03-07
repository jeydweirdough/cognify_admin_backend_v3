-- ============================================================
-- seed_changes.sql — Initial Dataset (Aligned with updated schema)
-- Run AFTER schema_changes.sql
--
-- PERMISSION IDs are sourced directly from frontend/permissions.ts
-- which is the single source of truth for all 33 permissions.
--
-- ROLE PERMISSION DESIGN:
--   ADMIN   — full access to all 33 permissions
--   FACULTY — scoped to curriculum, content, assessments, own
--             whitelist, student analytics, revisions, verification
--   STUDENT — mobile-only role; no web permissions granted
-- ============================================================

BEGIN;

-- ────────────────────────────────────────────────────────────
-- 0. PATCH CONSTRAINT
-- schema_changes.sql defines status CHECK ('ACTIVE','REMOVED') only.
-- PENDING is required for pre-created and self-registered users
-- awaiting admin approval. Patch the constraint here before any inserts.
-- ────────────────────────────────────────────────────────────
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_status_check;
ALTER TABLE users ADD CONSTRAINT users_status_check
    CHECK (status IN ('ACTIVE', 'PENDING', 'REMOVED'));

-- ────────────────────────────────────────────────────────────
-- 1. SYSTEM SETTINGS
-- ────────────────────────────────────────────────────────────
INSERT INTO system_settings (
    id, maintenance_mode, maintenance_banner,
    require_content_approval, allow_public_registration,
    institutional_passing_grade, institution_name, academic_year, updated_at
) VALUES (
    1, FALSE, NULL, TRUE, FALSE,
    75, 'Philippine Psychology Review Institute', '2024-2025', NOW()
) ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 2. ROLES
--
-- All permission IDs must exactly match frontend/permissions.ts.
-- Total: 33 permissions across 12 modules.
--
-- ON CONFLICT DO UPDATE ensures re-running this seed refreshes
-- permissions if they were changed in permissions.ts.
--
-- SIGN-UP FLOW (can_signup permission):
--   Roles with "can_signup" allow pre-created PENDING users to set
--   their password via POST /api/web/auth/signup.
--   After signup the user's status stays PENDING — they cannot log in
--   until an admin activates the account (sets status = 'ACTIVE').
-- ────────────────────────────────────────────────────────────
INSERT INTO roles (id, name, permissions, is_system, created_at) VALUES

-- ── ADMIN: full access — all permissions sourced from frontend/permissions.ts ─
-- Modules: dashboard (admin), curriculum, modules, verification, assessments,
--          revisions, analytics, users, students, whitelist, roles, security,
--          settings, authentication (web_login only — admins don't use mobile).
(
  '00000000-0000-0000-0000-000000000001',
  'ADMIN',
  '["view_admin_dashboard","view_subjects","create_subjects","edit_subjects","delete_subjects","view_content","create_content","edit_content","delete_content","view_verification","approve_verification","reject_verification","view_assessments","create_assessments","edit_assessments","delete_assessments","view_revisions","resolve_revisions","view_analytics","view_student_analytics","view_users","create_users","edit_users","delete_users","approve_users","view_students_nav","view_students","create_students","edit_students","delete_students","view_whitelist","add_whitelist","edit_whitelist","delete_whitelist","cross_check_whitelist","students_whitelist_only","view_roles","manage_roles","view_logs","view_settings","edit_settings","manage_backup","import_settings","web_login"]'::jsonb,
  TRUE, NOW()
),

-- ── FACULTY: scoped to curriculum, content, assessments, student management,
--   and student-only whitelist. Web app only (web_login).
--   Excluded: delete_*, admin dashboard, admin user-mgmt, roles, security logs,
--             system settings, full whitelist cross-check (admin only).
(
  '00000000-0000-0000-0000-000000000002',
  'FACULTY',
  '["view_faculty_dashboard","view_subjects","create_subjects","edit_subjects","view_content","create_content","edit_content","view_verification","approve_verification","reject_verification","view_assessments","create_assessments","edit_assessments","view_revisions","view_analytics","view_student_analytics","view_students_nav","view_students","create_students","edit_students","view_whitelist","add_whitelist","edit_whitelist","cross_check_whitelist","students_whitelist_only","web_login","can_signup"]'::jsonb,
  TRUE, NOW()
),

-- ── STUDENT: mobile-only role.
--   Each permission corresponds to one checkbox in Role Access Control.
--   mobile_login          → master gate: log in via mobile app
--   can_signup            → pre-created PENDING student can set their own password
--   --- Home Tab ---
--   mobile_view_home      → view home screen (readiness, quick actions)
--   mobile_save_mood      → save/update today's mood entry
--   mobile_delete_mood    → delete today's mood entry
--   --- Subjects ---
--   mobile_view_subjects  → browse subjects list + subject detail
--   --- Modules ---
--   mobile_view_modules   → read module text / PDF materials
--   mobile_track_recent_module → record recently viewed module
--   --- Assessments ---
--   mobile_view_assessments   → list assessments + view past results
--   mobile_submit_assessment  → submit answers and save result to DB
--   --- Progress ---
--   mobile_view_progress  → view readiness % and per-subject breakdown
--   --- Calendar & To-Do ---
--   mobile_view_calendar  → view study calendar with mood history
--   mobile_save_calendar_mood → save/update mood on a calendar date
--   mobile_add_session    → log a new study session to to-do list
--   --- Profile ---
--   mobile_view_profile   → view profile info, avatar, stats
--   mobile_edit_profile   → edit personal note and daily goal
--   --- Diagnostic ---
--   mobile_view_diagnostic   → view diagnostic intro + questions
--   mobile_submit_diagnostic → submit diagnostic answers (sets baseline)
--   --- Personal Space ---
--   mobile_view_binder    → access binders and saved notes
(
  '00000000-0000-0000-0000-000000000003',
  'STUDENT',
  '["mobile_login","can_signup","mobile_view_home","mobile_save_mood","mobile_delete_mood","mobile_view_subjects","mobile_view_modules","mobile_track_recent_module","mobile_view_assessments","mobile_submit_assessment","mobile_view_progress","mobile_view_calendar","mobile_save_calendar_mood","mobile_add_session","mobile_view_profile","mobile_edit_profile","mobile_view_diagnostic","mobile_submit_diagnostic","mobile_view_binder"]'::jsonb,
  TRUE, NOW()
)

ON CONFLICT (id) DO UPDATE
  SET permissions = EXCLUDED.permissions;

-- ────────────────────────────────────────────────────────────
-- 3. USERS
-- Passwords are bcrypt hashes (all accounts use "Password123!")
--
-- STATUS KEY:
--   ACTIVE  — can log in; fully operational account
--   PENDING — pre-created by admin OR signed up but not yet approved;
--             CANNOT log in until admin sets status = 'ACTIVE'
--   REMOVED — soft-deleted; blocked from login
--
-- Demo accounts:
--   student5  (PENDING, no password) — simulates pre-created, not yet signed up
--   student6  (PENDING, has password) — simulates signed-up but awaiting approval
-- ────────────────────────────────────────────────────────────
INSERT INTO users (
    id, cvsu_id, first_name, middle_name, last_name,
    email, password, role_id, status, department, date_created,
    registration_type, added_by, approved_by, approved_at
) VALUES
(
  '10000000-0000-0000-0000-000000000001',
  'ADMIN-001', 'Ana', 'Cruz', 'Reyes', 'admin@cvsu.edu.ph',
  '$2b$12$KIXbhELtNrGF7JK7CzIxiONH5V7M3G0GzGPHMK5JxGmE0s0P2yOZC',
  '00000000-0000-0000-0000-000000000001', 'ACTIVE', 'Administration',
  NOW() - INTERVAL '180 days',
  'MANUALLY_ADDED', NULL, NULL, NULL
),
(
  '10000000-0000-0000-0000-000000000002',
  'FAC-2024-001', 'Marco', 'Antonio', 'Santos', 'faculty1@cvsu.edu.ph',
  '$2b$12$X8RhYvBn7MtK3O4P5qAh8eP2Z3KMQd9hW1aJlH4yNxVRmUxS1sOaC',
  '00000000-0000-0000-0000-000000000002', 'ACTIVE', 'Developmental Psychology',
  NOW() - INTERVAL '150 days',
  'MANUALLY_ADDED', '10000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '150 days'
),
(
  '10000000-0000-0000-0000-000000000003',
  'FAC-2024-002', 'Elena', 'Grace', 'Villanueva', 'faculty2@cvsu.edu.ph',
  '$2b$12$X8RhYvBn7MtK3O4P5qAh8eP2Z3KMQd9hW1aJlH4yNxVRmUxS1sOaC',
  '00000000-0000-0000-0000-000000000002', 'ACTIVE', 'Clinical Psychology',
  NOW() - INTERVAL '120 days',
  'MANUALLY_ADDED', '10000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '120 days'
),
(
  '10000000-0000-0000-0000-000000000011',
  '2024-PSY-001', 'Jose', 'Miguel', 'Garcia', 'student1@cvsu.edu.ph',
  '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
  '00000000-0000-0000-0000-000000000003', 'ACTIVE', 'BS Psychology',
  NOW() - INTERVAL '90 days',
  'SELF_REGISTERED', NULL, '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '88 days'
),
(
  '10000000-0000-0000-0000-000000000012',
  '2024-PSY-002', 'Maria', 'Luisa', 'Fernandez', 'student2@cvsu.edu.ph',
  '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
  '00000000-0000-0000-0000-000000000003', 'ACTIVE', 'BS Psychology',
  NOW() - INTERVAL '85 days',
  'SELF_REGISTERED', NULL, '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '83 days'
),
-- student5: pre-created by admin, has not signed up yet (no password)
(
  '10000000-0000-0000-0000-000000000015',
  '2024-PSY-005', 'Diego', 'Luis', 'Bautista', 'student5@cvsu.edu.ph',
  NULL,
  '00000000-0000-0000-0000-000000000003', 'ACTIVE', 'BS Psychology',
  NOW() - INTERVAL '5 days',
  'MANUALLY_ADDED', '10000000-0000-0000-0000-000000000001', NULL, NULL
),
-- student6: self-registered (password set) but still PENDING admin approval
(
  '10000000-0000-0000-0000-000000000016',
  '2024-PSY-006', 'Sofia', 'Marie', 'Dela Cruz', 'student6@cvsu.edu.ph',
  '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
  '00000000-0000-0000-0000-000000000003', 'ACTIVE', 'BS Psychology',
  NOW() - INTERVAL '2 days',
  'SELF_REGISTERED', NULL, NULL, NULL
)
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 3.5 WHITELIST (sample entries)
-- Add two sample whitelist rows for demo/testing.
-- ────────────────────────────────────────────────────────────
INSERT INTO whitelist (
    id, first_name, middle_name, last_name,
    institutional_id, email, role, status, added_by, date_added
) VALUES
(
  '20000000-0000-0000-0000-000000000001',
  'Juan', NULL, 'Dela Cruz',
  '2024-PSY-WL-001', 'juan.delacruz@example.edu', 'STUDENT', 'PENDING', '10000000-0000-0000-0000-000000000001', NOW()
),
(
  '20000000-0000-0000-0000-000000000002',
  'Maria', 'L.', 'Santos',
  '2024-PSY-WL-002', 'maria.santos@example.edu', 'STUDENT', 'PENDING', '10000000-0000-0000-0000-000000000001', NOW()
)
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 4. SUBJECTS
-- ────────────────────────────────────────────────────────────
INSERT INTO subjects (id, name, description, color, weight, passing_rate, status, created_by, created_at, updated_at) VALUES
('30000000-0000-0000-0000-000000000001', 'Psychological Assessment',              'Theories, tools, and methods used to assess psychological attributes and mental health.',  '#6366f1', 40, 75, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '160 days', NOW() - INTERVAL '160 days'),
('30000000-0000-0000-0000-000000000002', 'Abnormal Psychology',                   'Classification, etiology, assessment, and treatment of psychological disorders.',          '#ec4899', 20, 75, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '155 days', NOW() - INTERVAL '155 days'),
('30000000-0000-0000-0000-000000000003', 'Developmental Psychology',              'Human development across the lifespan from infancy through late adulthood.',               '#8b5cf6', 20, 75, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '150 days', NOW() - INTERVAL '150 days'),
('30000000-0000-0000-0000-000000000004', 'Industrial / Organizational Psychology','Application of psychological principles to workplace behavior and organizational systems.', '#f59e0b', 20, 75, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '145 days', NOW() - INTERVAL '145 days')
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 5. MODULES
-- ────────────────────────────────────────────────────────────
INSERT INTO modules (id, subject_id, parent_id, title, description, content, type, format, file_url, file_name, sort_order, status, created_by, created_at) VALUES
('40000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', NULL, 'Introduction to Psychological Assessment', 'Overview of assessment principles and ethics.',    'Psychological assessment is the systematic process of gathering information about an individual using standardized tools, clinical interviews, and behavioral observations.',        'MODULE', 'TEXT', NULL, NULL, 1, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '158 days'),
('40000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000001', NULL, 'Reliability and Validity',                 'Psychometric foundations of assessment tools.',   'Reliability refers to consistency of measurement; validity refers to whether an instrument measures what it claims to measure. Both are essential for sound assessment practice.',   'MODULE', 'TEXT', NULL, NULL, 2, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '157 days'),
('40000000-0000-0000-0000-000000000003', '30000000-0000-0000-0000-000000000001', NULL, 'Intelligence and Cognitive Assessment',    'IQ testing, cognitive batteries, and interpretation.', NULL,                                                                                                                                                                              'MODULE', 'TEXT', NULL, NULL, 3, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '156 days'),
('40000000-0000-0000-0000-000000000004', '30000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000003', 'Wechsler Scales Guide', 'A comprehensive visual guide to the Wechsler intelligence scales.', NULL,                                                                                                                                             'MODULE', 'PDF',  'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf', 'wechsler_guide.pdf', 1, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '155 days'),
('40000000-0000-0000-0000-000000000005', '30000000-0000-0000-0000-000000000001', NULL, 'Psychological Assessment Handbook (E-Book)', 'Comprehensive e-book covering major assessment domains.', 'This e-book covers intelligence, personality, neuropsychological, and behavioral assessment tools used in clinical and educational settings.',                                   'E-BOOK', 'TEXT', NULL, NULL, 1, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '150 days'),
('40000000-0000-0000-0000-000000000006', '30000000-0000-0000-0000-000000000001', NULL, 'Personality Assessment Reference Guide',   'PDF reference e-book on projective and objective personality tests.', NULL,                                                                                                                                                           'E-BOOK', 'PDF',  'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf', 'personality_assessment_ebook.pdf', 2, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '145 days')
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 6. ASSESSMENTS
-- ────────────────────────────────────────────────────────────
INSERT INTO assessments (id, title, type, subject_id, module_id, items, status, author_id, created_at, updated_at) VALUES
('60000000-0000-0000-0000-000000000001', 'Psychological Assessment — Pre-Assessment', 'PRE_ASSESSMENT', '30000000-0000-0000-0000-000000000001', NULL,                                       5, 'APPROVED', '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '138 days', NOW() - INTERVAL '138 days'),
('60000000-0000-0000-0000-000000000002', 'Wechsler Scales — Quiz',                    'QUIZ',           '30000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000004',     5, 'APPROVED', '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '128 days', NOW() - INTERVAL '128 days')
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 7. QUESTIONS (correct_answer = 0-based index)
-- ────────────────────────────────────────────────────────────
INSERT INTO questions (id, assessment_id, author_id, text, options, correct_answer) VALUES
(gen_random_uuid(), '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002', 'Which of the following is a key characteristic of a standardized test?',         '["It is administered differently each time","It has uniform procedures for administration and scoring","It is only used for children","It does not require norms"]'::jsonb,          1),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002', 'Reliability in psychological assessment refers to:',                              '["Whether the test measures what it intends to","Consistency of measurement across time or raters","The breadth of content covered","The cultural fairness of items"]'::jsonb,        1),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002', 'Which validity type examines whether a test covers all aspects of a construct?', '["Predictive validity","Concurrent validity","Content validity","Construct validity"]'::jsonb,                                                                                        2),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002', 'A raw score is most useful when converted to a:',                                '["Percentile rank or standard score","Letter grade","Ratio score","Nominal category"]'::jsonb,                                                                                        0),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002', 'Informed consent in psychological assessment is primarily an issue of:',         '["Scoring accuracy","Test security","Professional ethics","Norm selection"]'::jsonb,                                                                                                  2),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 'The Wechsler scales yield which primary composite score?',                       '["Mental Age","Full Scale IQ","Deviation Quotient","Achievement Index"]'::jsonb,                                                                                                     1),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 'Which Wechsler index measures verbal reasoning and comprehension?',              '["Processing Speed Index","Visual Spatial Index","Verbal Comprehension Index","Fluid Reasoning Index"]'::jsonb,                                                                     2),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 'The Processing Speed Index in the Wechsler scales includes:',                   '["Similarities and Vocabulary","Block Design and Visual Puzzles","Coding and Symbol Search","Digit Span and Letter-Number Sequencing"]'::jsonb,                                    2),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 'A Wechsler subtest scaled score of 10 represents:',                             '["Below average performance","Average performance","Above average performance","Superior performance"]'::jsonb,                                                                    1),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 'Which version of the Wechsler scale is designed for adults aged 16–90?',        '["WPPSI-IV","WISC-V","WAIS-IV","WMS-IV"]'::jsonb,                                                                                                                                  2);

-- ────────────────────────────────────────────────────────────
-- 8. ASSESSMENT RESULTS
-- ────────────────────────────────────────────────────────────
INSERT INTO assessment_results (id, assessment_id, user_id, score, total_items, date_taken) VALUES
('70000000-0000-0000-0001-000000000001', '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000011', 3, 5, NOW() - INTERVAL '58 days'),
('70000000-0000-0000-0001-000000000002', '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000011', 5, 5, NOW() - INTERVAL '50 days'),
('70000000-0000-0000-0002-000000000001', '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000012', 4, 5, NOW() - INTERVAL '55 days')
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 9. REQUEST CHANGES
-- ────────────────────────────────────────────────────────────
INSERT INTO request_changes (id, target_id, created_by, type, content, revisions_list, status, created_at) VALUES
(
  'b0000000-0000-0000-0000-000000000001',
  '40000000-0000-0000-0000-000000000004',
  '10000000-0000-0000-0000-000000000002',
  'MODULE',
  '{"action":"UPDATE_MODULE","title":"Wechsler Scales Guide (Updated)","content":"Updated content: added section on WAIS-IV score interpretation and clinical applications."}'::jsonb,
  '[{"notes":"The section on index score interpretation is too brief. Please expand with clinical case examples.","status":"PENDING","author_id":"10000000-0000-0000-0000-000000000001"}]'::jsonb,
  'PENDING', NOW() - INTERVAL '3 days'
),
(
  'b0000000-0000-0000-0000-000000000002',
  '30000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000002',
  'SUBJECT',
  '{"action":"UPDATE_METADATA","name":"Psychological Assessment","description":"Expanded description covering neuropsychological and forensic assessment domains.","weight":40,"passingRate":80}'::jsonb,
  NULL, 'PENDING', NOW() - INTERVAL '1 day'
)
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 10. ACTIVITY LOGS
-- ────────────────────────────────────────────────────────────
INSERT INTO activity_logs (id, user_id, action, target, ip_address, created_at) VALUES
(gen_random_uuid(), '10000000-0000-0000-0000-000000000001', 'User logged in',          'admin@cvsu.edu.ph',                          '127.0.0.1', NOW() - INTERVAL '2 hours'),
(gen_random_uuid(), '10000000-0000-0000-0000-000000000002', 'Created new assessment',  'Psychological Assessment — Pre-Assessment',   '127.0.0.1', NOW() - INTERVAL '5 hours'),
(gen_random_uuid(), '10000000-0000-0000-0000-000000000001', 'Approved subject change', 'Psychological Assessment',                    '127.0.0.1', NOW() - INTERVAL '1 day')
ON CONFLICT DO NOTHING;

COMMIT;