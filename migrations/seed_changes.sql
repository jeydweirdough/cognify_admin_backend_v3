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
-- ────────────────────────────────────────────────────────────
INSERT INTO roles (id, name, permissions, is_system, created_at) VALUES

-- ── ADMIN: all 33 permissions ─────────────────────────────────────────────
(
  '00000000-0000-0000-0000-000000000001',
  'ADMIN',
  '["view_dashboard","view_subjects","create_subjects","edit_subjects","delete_subjects","view_content","create_content","edit_content","delete_content","verify_resources","view_assessments","create_assessments","edit_assessments","delete_assessments","view_revisions","resolve_revisions","view_analytics","view_student_analytics","export_analytics","view_users","create_users","edit_users","delete_users","view_whitelist","manage_whitelist","view_roles","manage_roles","view_logs","export_logs","view_settings","edit_settings","manage_backup","import_settings"]'::jsonb,
  TRUE, NOW()
),

-- ── FACULTY: 15 permissions — curriculum, content, assessments, students ──
-- Excluded: delete_*, resolve_revisions, user management, roles,
--           security logs, system settings, export_analytics
(
  '00000000-0000-0000-0000-000000000002',
  'FACULTY',
  '["view_dashboard","view_subjects","edit_subjects","view_content","create_content","edit_content","verify_resources","view_assessments","create_assessments","edit_assessments","view_revisions","view_analytics","view_student_analytics","view_whitelist","manage_whitelist","can_signup"]'::jsonb,
  TRUE, NOW()
),

-- ── STUDENT: can_signup only — activates account via web, then uses mobile app
(
  '00000000-0000-0000-0000-000000000003',
  'STUDENT',
  '["can_signup"]'::jsonb,
  TRUE, NOW()
)

ON CONFLICT (id) DO UPDATE
  SET permissions = EXCLUDED.permissions;

-- ────────────────────────────────────────────────────────────
-- 3. USERS
-- Passwords are bcrypt hashes (all accounts use "Password123!")
-- ────────────────────────────────────────────────────────────
INSERT INTO users (
    id, cvsu_id, first_name, middle_name, last_name,
    email, password, role_id, status, department, date_created
) VALUES
(
  '10000000-0000-0000-0000-000000000001',
  'ADMIN-001', 'Ana', 'Cruz', 'Reyes', 'admin@cvsu.edu.ph',
  '$2b$12$KIXbhELtNrGF7JK7CzIxiONH5V7M3G0GzGPHMK5JxGmE0s0P2yOZC',
  '00000000-0000-0000-0000-000000000001', 'ACTIVE', 'Administration',
  NOW() - INTERVAL '180 days'
),
(
  '10000000-0000-0000-0000-000000000002',
  'FAC-2024-001', 'Marco', 'Antonio', 'Santos', 'faculty1@cvsu.edu.ph',
  '$2b$12$X8RhYvBn7MtK3O4P5qAh8eP2Z3KMQd9hW1aJlH4yNxVRmUxS1sOaC',
  '00000000-0000-0000-0000-000000000002', 'ACTIVE', 'Developmental Psychology',
  NOW() - INTERVAL '150 days'
),
(
  '10000000-0000-0000-0000-000000000003',
  'FAC-2024-002', 'Elena', 'Grace', 'Villanueva', 'faculty2@cvsu.edu.ph',
  '$2b$12$X8RhYvBn7MtK3O4P5qAh8eP2Z3KMQd9hW1aJlH4yNxVRmUxS1sOaC',
  '00000000-0000-0000-0000-000000000002', 'ACTIVE', 'Clinical Psychology',
  NOW() - INTERVAL '120 days'
),
(
  '10000000-0000-0000-0000-000000000011',
  '2024-PSY-001', 'Jose', 'Miguel', 'Garcia', 'student1@cvsu.edu.ph',
  '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
  '00000000-0000-0000-0000-000000000003', 'ACTIVE', 'BS Psychology',
  NOW() - INTERVAL '90 days'
),
(
  '10000000-0000-0000-0000-000000000012',
  '2024-PSY-002', 'Maria', 'Luisa', 'Fernandez', 'student2@cvsu.edu.ph',
  '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
  '00000000-0000-0000-0000-000000000003', 'ACTIVE', 'BS Psychology',
  NOW() - INTERVAL '85 days'
),
(
  '10000000-0000-0000-0000-000000000015',
  '2024-PSY-005', 'Diego', 'Luis', 'Bautista', 'student5@cvsu.edu.ph',
  '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
  '00000000-0000-0000-0000-000000000003', 'PENDING', 'BS Psychology',
  NOW() - INTERVAL '5 days'
)
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 4. SUBJECTS
-- ────────────────────────────────────────────────────────────
INSERT INTO subjects (id, name, description, color, weight, passing_rate, status, created_by, created_at, updated_at) VALUES
('30000000-0000-0000-0000-000000000001', 'General Psychology',      'Foundational concepts, theories, and applications of psychology.',                          '#6366f1', 20, 75, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '160 days', NOW() - INTERVAL '160 days'),
('30000000-0000-0000-0000-000000000002', 'Developmental Psychology', 'Human development across the lifespan from infancy through late adulthood.',               '#8b5cf6', 20, 75, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '155 days', NOW() - INTERVAL '155 days'),
('30000000-0000-0000-0000-000000000003', 'Abnormal Psychology',      'Classification, etiology, assessment, and treatment of psychological disorders.',           '#ec4899', 20, 75, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '150 days', NOW() - INTERVAL '150 days')
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 5. MODULES
-- ────────────────────────────────────────────────────────────
INSERT INTO modules (id, subject_id, parent_id, title, description, content, type, format, file_url, file_name, sort_order, status, created_by, created_at) VALUES
('40000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', NULL, 'History and Schools of Thought',         'Major schools of psychology.',                    'Psychology evolved from philosophy and physiology. Wilhelm Wundt founded the first psychology lab in 1879.',                                                                        'MODULE', 'TEXT', NULL, NULL, 1, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '158 days'),
('40000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000001', NULL, 'Research Methods in Psychology',          'Scientific method and stats.',                    'The scientific method involves: identifying a problem, forming a hypothesis, designing a study, collecting data, analyzing results, drawing conclusions, and communicating findings.','MODULE', 'TEXT', NULL, NULL, 2, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '157 days'),
('40000000-0000-0000-0000-000000000003', '30000000-0000-0000-0000-000000000001', NULL, 'Biological Bases of Behavior',            'Nervous system and brain.',                       NULL,                                                                                                                                                                               'MODULE', 'TEXT', NULL, NULL, 3, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '156 days'),
('40000000-0000-0000-0000-000000000004', '30000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000003', 'Neurons and Neural Communication', 'A comprehensive visual guide to neural structures.', NULL,                                                                                                                                             'MODULE', 'PDF',  'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf', 'neurons_guide.pdf', 1, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '155 days'),
('40000000-0000-0000-0000-000000000005', '30000000-0000-0000-0000-000000000001', NULL, 'Introduction to Psychology (E-Book)',     'Comprehensive introductory e-book.',              'This e-book provides a thorough introduction to psychology, covering its history, major theoretical perspectives, and core research methodologies.',                                  'E-BOOK', 'TEXT', NULL, NULL, 1, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '150 days'),
('40000000-0000-0000-0000-000000000006', '30000000-0000-0000-0000-000000000001', NULL, 'Biological Psychology Reference Guide',  'PDF reference e-book on the neuroscience of behavior.', NULL,                                                                                                                                                                          'E-BOOK', 'PDF',  'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf', 'bio_psych_ebook.pdf', 2, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '145 days')
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 6. ASSESSMENTS
-- ────────────────────────────────────────────────────────────
INSERT INTO assessments (id, title, type, subject_id, module_id, items, status, author_id, created_at, updated_at) VALUES
('60000000-0000-0000-0000-000000000001', 'General Psychology — Pre-Assessment',       'PRE_ASSESSMENT', '30000000-0000-0000-0000-000000000001', NULL,                                       5, 'APPROVED', '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '138 days', NOW() - INTERVAL '138 days'),
('60000000-0000-0000-0000-000000000002', 'Neurons and Neural Communication — Quiz',   'QUIZ',           '30000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000004',     5, 'APPROVED', '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '128 days', NOW() - INTERVAL '128 days')
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 7. QUESTIONS (correct_answer = 0-based index)
-- ────────────────────────────────────────────────────────────
INSERT INTO questions (id, assessment_id, author_id, text, options, correct_answer) VALUES
(gen_random_uuid(), '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002', 'Who founded the first experimental psychology laboratory in 1879?',    '["Sigmund Freud","William James","Wilhelm Wundt","John Watson"]'::jsonb,                                                                          2),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002', 'Which approach emphasizes unconscious processes and early childhood?',  '["Behaviorism","Psychoanalysis","Humanism","Structuralism"]'::jsonb,                                                                              1),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002', 'The biopsychosocial model considers which three dimensions?',           '["Biological, psychological, social","Physical, mental, spiritual","Genetic, behavioral, cultural","Neural, cognitive, emotional"]'::jsonb,       0),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002', 'A researcher manipulates the IV and measures the DV. What type?',      '["Correlational","Naturalistic observation","Experiment","Case study"]'::jsonb,                                                                    2),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002', 'Which neurotransmitter is associated with reward and motivation?',      '["Serotonin","GABA","Dopamine","Acetylcholine"]'::jsonb,                                                                                           2),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 'What is the resting membrane potential of a typical neuron?',          '["-70 mV","+70 mV","-50 mV","0 mV"]'::jsonb,                                                                                                      0),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 'Which part of the neuron receives incoming signals?',                   '["Axon","Axon terminals","Dendrites","Myelin sheath"]'::jsonb,                                                                                     2),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 'The myelin sheath functions to:',                                       '["Generate neurotransmitters","Increase signal transmission speed","Store memories","Control hormones"]'::jsonb,                                 1),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 'Which neurotransmitter is the primary inhibitory neurotransmitter?',   '["Glutamate","Dopamine","GABA","Norepinephrine"]'::jsonb,                                                                                          2),
(gen_random_uuid(), '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 'The gap between two neurons is called:',                               '["Axon hillock","Synapse","Node of Ranvier","Soma"]'::jsonb,                                                                                       1);

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
  '{"action":"UPDATE_MODULE","title":"Neurons and Neural Communication (Updated)","content":"Updated content: added section on demyelinating diseases such as Multiple Sclerosis."}'::jsonb,
  '[{"notes":"The content on myelination is brief. Please add a section on demyelinating diseases.","status":"PENDING","author_id":"10000000-0000-0000-0000-000000000001"}]'::jsonb,
  'PENDING', NOW() - INTERVAL '3 days'
),
(
  'b0000000-0000-0000-0000-000000000002',
  '30000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000002',
  'SUBJECT',
  '{"action":"UPDATE_METADATA","name":"General Psychology","description":"Expanded description covering new topics.","weight":25,"passingRate":80}'::jsonb,
  NULL, 'PENDING', NOW() - INTERVAL '1 day'
)
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 10. ACTIVITY LOGS
-- ────────────────────────────────────────────────────────────
INSERT INTO activity_logs (id, user_id, action, target, ip_address, created_at) VALUES
(gen_random_uuid(), '10000000-0000-0000-0000-000000000001', 'User logged in',          'admin@cvsu.edu.ph',                   '127.0.0.1', NOW() - INTERVAL '2 hours'),
(gen_random_uuid(), '10000000-0000-0000-0000-000000000002', 'Created new assessment',  'General Psychology — Pre-Assessment', '127.0.0.1', NOW() - INTERVAL '5 hours'),
(gen_random_uuid(), '10000000-0000-0000-0000-000000000001', 'Approved subject change', 'General Psychology',                  '127.0.0.1', NOW() - INTERVAL '1 day')
ON CONFLICT DO NOTHING;

COMMIT;