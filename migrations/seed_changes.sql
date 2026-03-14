-- ============================================================
-- seed_changes.sql  —  Cognify  —  Seed Data
--
-- Run AFTER schema_changes.sql. setup.py does this automatically.
--
-- Permission IDs must exactly match frontend/permissions.ts
-- (the single source of truth for all permission strings).
--
-- ROLE PERMISSION DESIGN:
--   ADMIN   — full access to all permissions including TOS CRUD
--   FACULTY — scoped: curriculum, content, assessments,
--              student management, whitelist; no TOS/settings/roles
--   STUDENT — mobile-only role; no web permissions
--
-- All passwords in this file are bcrypt hashes of "Password123!"
-- Use setup.py → "Reset Dev Passwords" to change them all at once.
-- ============================================================

BEGIN;

-- ── 1. System Settings ───────────────────────────────────────
INSERT INTO system_settings (
    id, maintenance_mode, maintenance_banner,
    require_content_approval, allow_public_registration,
    institutional_passing_grade, institution_name, academic_year, updated_at
) VALUES (
    1, FALSE, NULL, TRUE, FALSE,
    75, 'Philippine Psychology Review Institute', '2024-2025', NOW()
) ON CONFLICT (id) DO NOTHING;

-- ── 2. Roles ─────────────────────────────────────────────────
-- ON CONFLICT DO UPDATE refreshes permissions when permissions.ts changes.
INSERT INTO roles (id, name, permissions, is_system, created_at) VALUES

-- ADMIN — full access including all 4 TOS permissions
(
  '00000000-0000-0000-0000-000000000001',
  'ADMIN',
  '["view_admin_dashboard","view_subjects","create_subjects","edit_subjects","delete_subjects","view_content","create_content","edit_content","delete_content","view_verification","approve_verification","reject_verification","view_assessments","create_assessments","edit_assessments","delete_assessments","view_revisions","resolve_revisions","view_analytics","view_student_analytics","view_users","create_users","edit_users","delete_users","approve_users","view_students_nav","view_students","create_students","edit_students","delete_students","approve_pending_students","view_whitelist","add_whitelist","edit_whitelist","delete_whitelist","cross_check_whitelist","students_whitelist_only","view_roles","manage_roles","view_logs","view_settings","edit_settings","manage_backup","import_settings","view_tos","create_tos","edit_tos","delete_tos","web_login"]'::jsonb,
  TRUE, NOW()
),

-- FACULTY — scoped; no TOS, no delete_*, no admin user-mgmt, roles, security, settings
(
  '00000000-0000-0000-0000-000000000002',
  'FACULTY',
  '["view_faculty_dashboard","view_subjects","create_subjects","edit_subjects","view_content","create_content","edit_content","view_verification","approve_verification","reject_verification","view_assessments","create_assessments","edit_assessments","view_revisions","view_analytics","view_student_analytics","view_students_nav","view_students","create_students","edit_students","view_whitelist","add_whitelist","edit_whitelist","cross_check_whitelist","students_whitelist_only","web_login","can_signup"]'::jsonb,
  TRUE, NOW()
),

-- STUDENT — mobile-only role
(
  '00000000-0000-0000-0000-000000000003',
  'STUDENT',
  '["mobile_login","can_signup","mobile_view_home","mobile_save_mood","mobile_delete_mood","mobile_view_subjects","mobile_view_modules","mobile_track_recent_module","mobile_view_assessments","mobile_submit_assessment","mobile_view_progress","mobile_view_calendar","mobile_save_calendar_mood","mobile_add_session","mobile_view_profile","mobile_edit_profile","mobile_view_diagnostic","mobile_submit_diagnostic","mobile_view_binder"]'::jsonb,
  TRUE, NOW()
)

ON CONFLICT (id) DO UPDATE SET permissions = EXCLUDED.permissions;

-- ── 3. Users ──────────────────────────────────────────────────
-- STATUS:
--   ACTIVE  — can log in
--   PENDING — signed up or pre-created but awaiting admin approval
--   REMOVED — soft-deleted; blocked from login
--
-- Demo edge cases:
--   student5 — pre-created by admin, no password yet
--   student6 — self-registered (has password) but still PENDING
INSERT INTO users (
    id, cvsu_id, first_name, middle_name, last_name,
    email, password, role_id, status, department, date_created,
    registration_type, added_by, approved_by, approved_at
) VALUES
(
  '10000000-0000-0000-0000-000000000001',
  'ADMIN-001','Ana','Cruz','Reyes','admin@cvsu.edu.ph',
  '$2b$12$KIXbhELtNrGF7JK7CzIxiONH5V7M3G0GzGPHMK5JxGmE0s0P2yOZC',
  '00000000-0000-0000-0000-000000000001','ACTIVE','Administration',
  NOW()-INTERVAL '180 days','MANUALLY_ADDED',NULL,NULL,NULL
),
(
  '10000000-0000-0000-0000-000000000002',
  'FAC-2024-001','Marco','Antonio','Santos','faculty1@cvsu.edu.ph',
  '$2b$12$X8RhYvBn7MtK3O4P5qAh8eP2Z3KMQd9hW1aJlH4yNxVRmUxS1sOaC',
  '00000000-0000-0000-0000-000000000002','ACTIVE','Developmental Psychology',
  NOW()-INTERVAL '150 days','MANUALLY_ADDED',
  '10000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000001',
  NOW()-INTERVAL '150 days'
),
(
  '10000000-0000-0000-0000-000000000003',
  'FAC-2024-002','Elena','Grace','Villanueva','faculty2@cvsu.edu.ph',
  '$2b$12$X8RhYvBn7MtK3O4P5qAh8eP2Z3KMQd9hW1aJlH4yNxVRmUxS1sOaC',
  '00000000-0000-0000-0000-000000000002','ACTIVE','Clinical Psychology',
  NOW()-INTERVAL '120 days','MANUALLY_ADDED',
  '10000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000001',
  NOW()-INTERVAL '120 days'
),
(
  '10000000-0000-0000-0000-000000000011',
  '2024-PSY-001','Jose','Miguel','Garcia','student1@cvsu.edu.ph',
  '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
  '00000000-0000-0000-0000-000000000003','ACTIVE','BS Psychology',
  NOW()-INTERVAL '90 days','SELF_REGISTERED',NULL,
  '10000000-0000-0000-0000-000000000001',NOW()-INTERVAL '88 days'
),
(
  '10000000-0000-0000-0000-000000000012',
  '2024-PSY-002','Maria','Luisa','Fernandez','student2@cvsu.edu.ph',
  '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
  '00000000-0000-0000-0000-000000000003','ACTIVE','BS Psychology',
  NOW()-INTERVAL '85 days','SELF_REGISTERED',NULL,
  '10000000-0000-0000-0000-000000000001',NOW()-INTERVAL '83 days'
),
-- Pre-created; no password yet (hasn't signed up)
(
  '10000000-0000-0000-0000-000000000015',
  '2024-PSY-005','Diego','Luis','Bautista','student5@cvsu.edu.ph',
  NULL,
  '00000000-0000-0000-0000-000000000003','ACTIVE','BS Psychology',
  NOW()-INTERVAL '5 days','MANUALLY_ADDED',
  '10000000-0000-0000-0000-000000000001',NULL,NULL
),
-- Self-registered (has password) but awaiting approval → PENDING
(
  '10000000-0000-0000-0000-000000000016',
  '2024-PSY-006','Sofia','Marie','Dela Cruz','student6@cvsu.edu.ph',
  '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
  '00000000-0000-0000-0000-000000000003','ACTIVE','BS Psychology',
  NOW()-INTERVAL '2 days','SELF_REGISTERED',NULL,NULL,NULL
)
ON CONFLICT (id) DO NOTHING;

-- ── 4. Subjects ───────────────────────────────────────────────
INSERT INTO subjects (id, name, description, color, weight, passing_rate, status, created_by, created_at, updated_at) VALUES
('30000000-0000-0000-0000-000000000001','Psychological Assessment',              'Theories, tools, and methods used to assess psychological attributes and mental health.',  '#6366f1',40,75,'APPROVED','10000000-0000-0000-0000-000000000001',NOW()-INTERVAL '160 days',NOW()-INTERVAL '160 days'),
('30000000-0000-0000-0000-000000000002','Abnormal Psychology',                   'Classification, etiology, assessment, and treatment of psychological disorders.',          '#ec4899',20,75,'APPROVED','10000000-0000-0000-0000-000000000001',NOW()-INTERVAL '155 days',NOW()-INTERVAL '155 days'),
('30000000-0000-0000-0000-000000000003','Developmental Psychology',              'Human development across the lifespan from infancy through late adulthood.',               '#8b5cf6',20,75,'APPROVED','10000000-0000-0000-0000-000000000001',NOW()-INTERVAL '150 days',NOW()-INTERVAL '150 days'),
('30000000-0000-0000-0000-000000000004','Industrial / Organizational Psychology','Application of psychological principles to workplace behavior and organizational systems.','#f59e0b',20,75,'APPROVED','10000000-0000-0000-0000-000000000001',NOW()-INTERVAL '145 days',NOW()-INTERVAL '145 days')
ON CONFLICT (id) DO NOTHING;

-- ── 5. Modules ────────────────────────────────────────────────
INSERT INTO modules (id, subject_id, parent_id, title, description, content, type, format, file_url, file_name, sort_order, status, created_by, created_at) VALUES
('40000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001',NULL,'Introduction to Psychological Assessment','Overview of assessment principles and ethics.','Psychological assessment is the systematic process of gathering information about an individual using standardized tools, clinical interviews, and behavioral observations.','MODULE','TEXT',NULL,NULL,1,'APPROVED','10000000-0000-0000-0000-000000000001',NOW()-INTERVAL '158 days'),
('40000000-0000-0000-0000-000000000002','30000000-0000-0000-0000-000000000001',NULL,'Reliability and Validity','Psychometric foundations of assessment tools.','Reliability refers to consistency of measurement; validity refers to whether an instrument measures what it claims to measure. Both are essential for sound assessment practice.','MODULE','TEXT',NULL,NULL,2,'APPROVED','10000000-0000-0000-0000-000000000001',NOW()-INTERVAL '157 days'),
('40000000-0000-0000-0000-000000000003','30000000-0000-0000-0000-000000000001',NULL,'Intelligence and Cognitive Assessment','IQ testing, cognitive batteries, and interpretation.',NULL,'MODULE','TEXT',NULL,NULL,3,'APPROVED','10000000-0000-0000-0000-000000000001',NOW()-INTERVAL '156 days'),
('40000000-0000-0000-0000-000000000004','30000000-0000-0000-0000-000000000001','40000000-0000-0000-0000-000000000003','Wechsler Scales Guide','A comprehensive visual guide to the Wechsler intelligence scales.',NULL,'MODULE','PDF','https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf','wechsler_guide.pdf',1,'APPROVED','10000000-0000-0000-0000-000000000001',NOW()-INTERVAL '155 days'),
('40000000-0000-0000-0000-000000000005','30000000-0000-0000-0000-000000000001',NULL,'Psychological Assessment Handbook (E-Book)','Comprehensive e-book covering major assessment domains.','This e-book covers intelligence, personality, neuropsychological, and behavioral assessment tools used in clinical and educational settings.','E-BOOK','TEXT',NULL,NULL,1,'APPROVED','10000000-0000-0000-0000-000000000001',NOW()-INTERVAL '150 days'),
('40000000-0000-0000-0000-000000000006','30000000-0000-0000-0000-000000000001',NULL,'Personality Assessment Reference Guide','PDF reference e-book on projective and objective personality tests.',NULL,'E-BOOK','PDF','https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf','personality_assessment_ebook.pdf',2,'APPROVED','10000000-0000-0000-0000-000000000001',NOW()-INTERVAL '145 days')
ON CONFLICT (id) DO NOTHING;

-- ── 6. Assessments ────────────────────────────────────────────
INSERT INTO assessments (id, title, type, subject_id, module_id, items, status, author_id, created_at, updated_at) VALUES
('60000000-0000-0000-0000-000000000001','Psychological Assessment - Pre-Assessment','PRE_ASSESSMENT','30000000-0000-0000-0000-000000000001',NULL,5,'APPROVED','10000000-0000-0000-0000-000000000002',NOW()-INTERVAL '138 days',NOW()-INTERVAL '138 days'),
('60000000-0000-0000-0000-000000000002','Wechsler Scales - Quiz','QUIZ','30000000-0000-0000-0000-000000000001','40000000-0000-0000-0000-000000000004',5,'APPROVED','10000000-0000-0000-0000-000000000002',NOW()-INTERVAL '128 days',NOW()-INTERVAL '128 days')
ON CONFLICT (id) DO NOTHING;

-- ── 7. Questions ──────────────────────────────────────────────
INSERT INTO questions (id, assessment_id, author_id, text, options, correct_answer) VALUES
(gen_random_uuid(),'60000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000002','Which of the following is a key characteristic of a standardized test?','["It is administered differently each time","It has uniform procedures for administration and scoring","It is only used for children","It does not require norms"]'::jsonb,1),
(gen_random_uuid(),'60000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000002','Reliability in psychological assessment refers to:','["Whether the test measures what it intends to","Consistency of measurement across time or raters","The breadth of content covered","The cultural fairness of items"]'::jsonb,1),
(gen_random_uuid(),'60000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000002','Which validity type examines whether a test covers all aspects of a construct?','["Predictive validity","Concurrent validity","Content validity","Construct validity"]'::jsonb,2),
(gen_random_uuid(),'60000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000002','A raw score is most useful when converted to a:','["Percentile rank or standard score","Letter grade","Ratio score","Nominal category"]'::jsonb,0),
(gen_random_uuid(),'60000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000002','Informed consent in psychological assessment is primarily an issue of:','["Scoring accuracy","Test security","Professional ethics","Norm selection"]'::jsonb,2),
(gen_random_uuid(),'60000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000002','The Wechsler scales yield which primary composite score?','["Mental Age","Full Scale IQ","Deviation Quotient","Achievement Index"]'::jsonb,1),
(gen_random_uuid(),'60000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000002','Which Wechsler index measures verbal reasoning and comprehension?','["Processing Speed Index","Visual Spatial Index","Verbal Comprehension Index","Fluid Reasoning Index"]'::jsonb,2),
(gen_random_uuid(),'60000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000002','The Processing Speed Index in the Wechsler scales includes:','["Similarities and Vocabulary","Block Design and Visual Puzzles","Coding and Symbol Search","Digit Span and Letter-Number Sequencing"]'::jsonb,2),
(gen_random_uuid(),'60000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000002','A Wechsler subtest scaled score of 10 represents:','["Below average performance","Average performance","Above average performance","Superior performance"]'::jsonb,1),
(gen_random_uuid(),'60000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000002','Which version of the Wechsler scale is designed for adults aged 16-90?','["WPPSI-IV","WISC-V","WAIS-IV","WMS-IV"]'::jsonb,2);

-- ── 8. Assessment Results ─────────────────────────────────────
INSERT INTO assessment_results (id, assessment_id, user_id, score, total_items, date_taken) VALUES
('70000000-0000-0000-0001-000000000001','60000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000011',3,5,NOW()-INTERVAL '58 days'),
('70000000-0000-0000-0001-000000000002','60000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000011',5,5,NOW()-INTERVAL '50 days'),
('70000000-0000-0000-0002-000000000001','60000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000012',4,5,NOW()-INTERVAL '55 days')
ON CONFLICT (id) DO NOTHING;

-- ── 9. Request Changes ────────────────────────────────────────
INSERT INTO request_changes (id, target_id, created_by, type, content, revisions_list, status, created_at) VALUES
(
  'b0000000-0000-0000-0000-000000000001',
  '40000000-0000-0000-0000-000000000004',
  '10000000-0000-0000-0000-000000000002',
  'MODULE',
  '{"action":"UPDATE_MODULE","title":"Wechsler Scales Guide (Updated)","content":"Updated content: added section on WAIS-IV score interpretation and clinical applications."}'::jsonb,
  '[{"notes":"The section on index score interpretation is too brief. Please expand with clinical case examples.","status":"PENDING","author_id":"10000000-0000-0000-0000-000000000001"}]'::jsonb,
  'PENDING',NOW()-INTERVAL '3 days'
),
(
  'b0000000-0000-0000-0000-000000000002',
  '30000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000002',
  'SUBJECT',
  '{"action":"UPDATE_METADATA","name":"Psychological Assessment","description":"Expanded description covering neuropsychological and forensic assessment domains.","weight":40,"passingRate":80}'::jsonb,
  NULL,'PENDING',NOW()-INTERVAL '1 day'
)
ON CONFLICT (id) DO NOTHING;

-- ── 10. Activity Logs ─────────────────────────────────────────
INSERT INTO activity_logs (id, user_id, action, target, ip_address, created_at) VALUES
(gen_random_uuid(),'10000000-0000-0000-0000-000000000001','User logged in',         'admin@cvsu.edu.ph',                        '127.0.0.1',NOW()-INTERVAL '2 hours'),
(gen_random_uuid(),'10000000-0000-0000-0000-000000000002','Created new assessment', 'Psychological Assessment - Pre-Assessment', '127.0.0.1',NOW()-INTERVAL '5 hours'),
(gen_random_uuid(),'10000000-0000-0000-0000-000000000001','Approved subject change','Psychological Assessment',                  '127.0.0.1',NOW()-INTERVAL '1 day')
ON CONFLICT DO NOTHING;

COMMIT;