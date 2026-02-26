-- ================================================================
-- SEED DATA
-- Run this AFTER schema.sql
-- Order: roles → users → system_settings → subjects → modules
--        → assessments → questions → assessment_questions
-- ================================================================


-- ================================================================
-- ROLES
-- Permissions model: { "pages": { "<page>": ["create","retrieve","update","delete"] } }
-- ================================================================

INSERT INTO roles (id, name, permissions, is_system) VALUES

-- ADMIN: full access to everything
(
  'aa000000-0000-0000-0000-000000000001',
  'ADMIN',
  '{
    "pages": {
      "dashboard":    ["create","retrieve","update","delete"],
      "subjects":     ["create","retrieve","update","delete"],
      "modules":      ["create","retrieve","update","delete"],
      "assessments":  ["create","retrieve","update","delete"],
      "questions":    ["create","retrieve","update","delete"],
      "users":        ["create","retrieve","update","delete"],
      "revisions":    ["create","retrieve","update","delete"],
      "verification": ["create","retrieve","update","delete"],
      "settings":     ["create","retrieve","update","delete"],
      "results":      ["retrieve"]
    }
  }',
  TRUE
),

-- FACULTY: can create and manage content, submit for review, cannot manage users or settings
(
  'aa000000-0000-0000-0000-000000000002',
  'FACULTY',
  '{
    "pages": {
      "dashboard":    ["retrieve"],
      "subjects":     ["create","retrieve","update"],
      "modules":      ["create","retrieve","update"],
      "assessments":  ["create","retrieve","update"],
      "questions":    ["create","retrieve","update"],
      "revisions":    ["create","retrieve"],
      "results":      ["retrieve"]
    }
  }',
  TRUE
),

-- STUDENT: read-only access to learning content, can take assessments and view own results
(
  'aa000000-0000-0000-0000-000000000003',
  'STUDENT',
  '{
    "pages": {
      "dashboard":   ["retrieve"],
      "subjects":    ["retrieve"],
      "modules":     ["retrieve"],
      "assessments": ["retrieve","create"],
      "results":     ["retrieve"]
    }
  }',
  TRUE
);


-- ================================================================
-- USERS
-- 3 admins, 5 faculty, 12 students — all BSPsych
-- Varied status: ACTIVE / DEACTIVATED / PENDING
-- ================================================================

INSERT INTO users (id, first_name, middle_name, last_name, email, password, department, role_id, status, date_created, last_updated, last_login) VALUES

-- ADMINS
(
  '00000000-0000-0000-0001-000000000001', 'Maria', 'Santos',  'Reyes',
  'maria.reyes@cvsu-bacoor.edu.ph',   '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000001', 'ACTIVE',
  '2024-06-01 08:00:00', '2026-02-20 09:15:00', '2026-02-23 08:00:00'
),
(
  '00000000-0000-0000-0001-000000000002', 'Jose',  'Cruz',    'Dela Cruz',
  'jose.delacruz@cvsu-bacoor.edu.ph', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000001', 'ACTIVE',
  '2024-06-01 08:00:00', '2026-01-15 10:00:00', '2026-02-22 14:30:00'
),
(
  '00000000-0000-0000-0001-000000000003', 'Ana',   'Bautista', 'Garcia',
  'ana.garcia@cvsu-bacoor.edu.ph',    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000001', 'ACTIVE',
  '2024-06-01 08:00:00', '2025-11-10 11:00:00', '2026-02-21 16:00:00'
),

-- FACULTY
(
  '00000000-0000-0000-0002-000000000001', 'Carlos',   'Mendoza',  'Villanueva',
  'carlos.villanueva@cvsu-bacoor.edu.ph', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000002', 'ACTIVE',
  '2024-07-15 09:00:00', '2026-02-18 08:30:00', '2026-02-23 07:45:00'
),
(
  '00000000-0000-0000-0002-000000000002', 'Liza',     'Torres',   'Navarro',
  'liza.navarro@cvsu-bacoor.edu.ph',     '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000002', 'ACTIVE',
  '2024-07-15 09:00:00', '2026-02-10 13:00:00', '2026-02-20 09:00:00'
),
(
  '00000000-0000-0000-0002-000000000003', 'Ramon',    'Aquino',   'Soriano',
  'ramon.soriano@cvsu-bacoor.edu.ph',    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000002', 'ACTIVE',
  '2024-08-01 09:00:00', '2025-12-05 10:15:00', '2026-02-19 11:30:00'
),
(
  '00000000-0000-0000-0002-000000000004', 'Elena',    'Ramos',    'Castillo',
  'elena.castillo@cvsu-bacoor.edu.ph',   '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000002', 'ACTIVE',
  '2024-08-01 09:00:00', '2026-01-28 15:00:00', '2026-02-17 14:00:00'
),
(
  '00000000-0000-0000-0002-000000000005', 'Miguel',   'Flores',   'Ibarra',
  'miguel.ibarra@cvsu-bacoor.edu.ph',    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000002', 'DEACTIVATED',
  '2024-08-01 09:00:00', '2025-09-01 08:00:00', '2025-08-30 10:00:00'
),

-- STUDENTS
(
  '00000000-0000-0000-0003-000000000001', 'Sofia',    'Reyes',    'Aguilar',
  'sofia.aguilar@student.cvsu-bacoor.edu.ph',   '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000003', 'ACTIVE',
  '2025-06-10 10:00:00', '2026-02-22 08:00:00', '2026-02-23 07:00:00'
),
(
  '00000000-0000-0000-0003-000000000002', 'Marco',    'Lim',      'Santos',
  'marco.santos@student.cvsu-bacoor.edu.ph',    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000003', 'ACTIVE',
  '2025-06-10 10:00:00', '2026-02-21 09:30:00', '2026-02-22 18:00:00'
),
(
  '00000000-0000-0000-0003-000000000003', 'Bianca',   'Cruz',     'Mendoza',
  'bianca.mendoza@student.cvsu-bacoor.edu.ph',  '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000003', 'ACTIVE',
  '2025-06-10 10:00:00', '2026-02-20 11:00:00', '2026-02-23 06:45:00'
),
(
  '00000000-0000-0000-0003-000000000004', 'Paolo',    'Garcia',   'Fernandez',
  'paolo.fernandez@student.cvsu-bacoor.edu.ph', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000003', 'ACTIVE',
  '2025-06-11 10:00:00', '2026-02-19 14:00:00', '2026-02-22 20:00:00'
),
(
  '00000000-0000-0000-0003-000000000005', 'Katrina',  'Diaz',     'Ramos',
  'katrina.ramos@student.cvsu-bacoor.edu.ph',   '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000003', 'ACTIVE',
  '2025-06-11 10:00:00', '2026-02-18 16:00:00', '2026-02-21 08:30:00'
),
(
  '00000000-0000-0000-0003-000000000006', 'Luis',     'Tan',      'Aquino',
  'luis.aquino@student.cvsu-bacoor.edu.ph',     '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000003', 'ACTIVE',
  '2025-06-12 10:00:00', '2026-02-17 10:00:00', '2026-02-22 12:00:00'
),
(
  '00000000-0000-0000-0003-000000000007', 'Angela',   'Bautista', 'Torres',
  'angela.torres@student.cvsu-bacoor.edu.ph',   '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000003', 'ACTIVE',
  '2025-06-12 10:00:00', '2026-02-16 09:00:00', '2026-02-20 19:00:00'
),
(
  '00000000-0000-0000-0003-000000000008', 'Rafael',   'Navarro',  'Villanueva',
  'rafael.villanueva@student.cvsu-bacoor.edu.ph','$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000003', 'ACTIVE',
  '2025-06-13 10:00:00', '2026-02-15 11:00:00', '2026-02-21 15:00:00'
),
(
  '00000000-0000-0000-0003-000000000009', 'Camille',  'Soriano',  'De Leon',
  'camille.deleon@student.cvsu-bacoor.edu.ph',  '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000003', 'PENDING',
  '2026-02-20 14:00:00', '2026-02-20 14:00:00', '2026-02-20 14:00:00'
),
(
  '00000000-0000-0000-0003-000000000010', 'Nico',     'Castillo', 'Flores',
  'nico.flores@student.cvsu-bacoor.edu.ph',     '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000003', 'PENDING',
  '2026-02-21 09:00:00', '2026-02-21 09:00:00', '2026-02-21 09:00:00'
),
(
  '00000000-0000-0000-0003-000000000011', 'Tricia',   'Ibarra',   'Pascual',
  'tricia.pascual@student.cvsu-bacoor.edu.ph',  '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000003', 'DEACTIVATED',
  '2025-06-10 10:00:00', '2025-10-01 08:00:00', '2025-09-28 10:00:00'
),
(
  '00000000-0000-0000-0003-000000000012', 'Gab',      'Pascual',  'Medina',
  'gab.medina@student.cvsu-bacoor.edu.ph',      '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewh5TY4uMmyeGmPu', 'BSPsych',
  'aa000000-0000-0000-0000-000000000003', 'ACTIVE',
  '2025-06-14 10:00:00', '2026-02-22 10:00:00', '2026-02-23 06:00:00'
);


-- ================================================================
-- SYSTEM SETTINGS
-- ================================================================

INSERT INTO system_settings (id, academic_year, institutional_name, maintenance_mode) VALUES
(
  'dd000000-0000-0000-0000-000000000001',
  '2025-2026',
  'BS Psychology CvSU - Bacoor Admin',
  FALSE
);


-- ================================================================
-- SUBJECTS
-- author = first admin user
-- weight stored in description metadata note: weight is not in
-- the schema column-wise so we add it as a column suggestion below,
-- OR store in a future metadata JSONB. For now added as a schema
-- ALTER so the seed can populate it properly.
-- ================================================================

INSERT INTO subjects (id, name, description, color, weight, passing_rate, status, author_id, date_created, last_updated) VALUES

(
  'bb000000-0000-0000-0000-000000000001',
  'Developmental Psychology',
  'Scientific study of human development across the lifespan, covering biological, cognitive, social, and emotional domains.',
  '#1e40af', 20, 60, 'APPROVED',
  '00000000-0000-0000-0001-000000000001',
  '2026-02-23 08:00:00', '2026-02-23 08:00:00'
),
(
  'bb000000-0000-0000-0000-000000000002',
  'Abnormal Psychology',
  'Examination of psychopathology, diagnostic frameworks, etiology, and evidence-based treatment approaches.',
  '#b91c1c', 20, 60, 'APPROVED',
  '00000000-0000-0000-0001-000000000001',
  '2026-02-23 08:00:00', '2026-02-23 08:00:00'
),
(
  'bb000000-0000-0000-0000-000000000003',
  'Industrial / Organizational Psychology',
  'Application of psychological principles to workplace behavior, talent systems, and organizational effectiveness.',
  '#047857', 20, 60, 'APPROVED',
  '00000000-0000-0000-0001-000000000001',
  '2026-02-23 08:00:00', '2026-02-23 08:00:00'
),
(
  'bb000000-0000-0000-0000-000000000004',
  'Psychological Assessment',
  'Psychometric principles, test administration, interpretation, and integrated psychological reporting.',
  '#7c3aed', 40, 60, 'APPROVED',
  '00000000-0000-0000-0001-000000000001',
  '2026-02-23 08:00:00', '2026-02-23 08:00:00'
);


-- ================================================================
-- MODULES
-- Based on the topics in the JSON data.
-- author = first faculty member
-- ================================================================

INSERT INTO modules (id, subject_id, author_id, title, file_name, file_url, format, status, date_created, last_updated) VALUES

-- Developmental Psychology (9 modules)
('cc000001-0000-0000-0000-000000000001', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Developmental Psychology - Prenatal',                  'DevPsy_1_Prenatal-Copy-2.pdf',              '/Lectures - Handouts/Developmental Psychology/DevPsy_1_Prenatal-Copy-2.pdf',              'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000001-0000-0000-0000-000000000002', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Developmental Psychology - Infancy',                   'DevPsy_2_Infancy-Copy-2.pdf',               '/Lectures - Handouts/Developmental Psychology/DevPsy_2_Infancy-Copy-2.pdf',               'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000001-0000-0000-0000-000000000003', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Developmental Psychology - Early Childhood',           'DevPsy_3_EarlyChildhood-Copy-Copy.pdf',     '/Lectures - Handouts/Developmental Psychology/DevPsy_3_EarlyChildhood-Copy-Copy.pdf',     'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000001-0000-0000-0000-000000000004', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Developmental Psychology - Middle and Late Childhood', 'DevPsy_4_MiddleAndLateChildhood-Copy.pdf',  '/Lectures - Handouts/Developmental Psychology/DevPsy_4_MiddleAndLateChildhood-Copy.pdf',  'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000001-0000-0000-0000-000000000005', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Developmental Psychology - Adolescence',               'DevPsy_5_Adolescence.pdf',                  '/Lectures - Handouts/Developmental Psychology/DevPsy_5_Adolescence.pdf',                  'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000001-0000-0000-0000-000000000006', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Developmental Psychology - Young Adulthood',           'DevPsy_6_YoungAdulthood.pdf',               '/Lectures - Handouts/Developmental Psychology/DevPsy_6_YoungAdulthood.pdf',               'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000001-0000-0000-0000-000000000007', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Developmental Psychology - Middle Adulthood',          'DevPsy_7_MiddleAdulthood.pdf',              '/Lectures - Handouts/Developmental Psychology/DevPsy_7_MiddleAdulthood.pdf',              'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000001-0000-0000-0000-000000000008', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Developmental Psychology - Old Age',                   'DevPsy_8_OldAge.pdf',                       '/Lectures - Handouts/Developmental Psychology/DevPsy_8_OldAge.pdf',                       'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000001-0000-0000-0000-000000000009', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Developmental Psychology - Death',                     'DevPsy_9_Death.pdf',                        '/Lectures - Handouts/Developmental Psychology/DevPsy_9_Death.pdf',                        'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- Abnormal Psychology (5 modules)
('cc000002-0000-0000-0000-000000000001', 'bb000000-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Abnormal Psychology - Phase 1', 'AbPsy_Phase1_.pdf',   '/Lectures - Handouts/Abnormal Psychology/AbPsy_Phase1_.pdf',   'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000002-0000-0000-0000-000000000002', 'bb000000-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Abnormal Psychology - Phase 2', 'AbPsy_Phase2_.pdf',   '/Lectures - Handouts/Abnormal Psychology/AbPsy_Phase2_.pdf',   'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000002-0000-0000-0000-000000000003', 'bb000000-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Abnormal Psychology - Phase 3', 'AbPsy_Phase3_.pdf',   '/Lectures - Handouts/Abnormal Psychology/AbPsy_Phase3_.pdf',   'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000002-0000-0000-0000-000000000004', 'bb000000-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Abnormal Psychology - Phase 4', 'AbPsy_Phase4_-1.pdf', '/Lectures - Handouts/Abnormal Psychology/AbPsy_Phase4_-1.pdf', 'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000002-0000-0000-0000-000000000005', 'bb000000-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Abnormal Psychology - Phase 5', 'AbPsy_Phase5_.pdf',   '/Lectures - Handouts/Abnormal Psychology/AbPsy_Phase5_.pdf',   'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- Industrial / Organizational Psychology (3 modules)
('cc000003-0000-0000-0000-000000000001', 'bb000000-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000003', 'Introduction to Industrial Psychology', 'Introduction to Industrial Psychology.pdf', '/Lectures - Handouts/Industrial Organizational Psychology/Introduction to Industrial Psychology.pdf', 'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000003-0000-0000-0000-000000000002', 'bb000000-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000003', 'Legal Issues',                         'Legal Issues.pdf',                          '/Lectures - Handouts/Industrial Organizational Psychology/Legal Issues.pdf',                          'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000003-0000-0000-0000-000000000003', 'bb000000-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000003', 'Employee Selection',                   '4. Employee Selection.pdf',                 '/Lectures - Handouts/Industrial Organizational Psychology/4. Employee Selection.pdf',                 'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- Psychological Assessment (3 modules)
('cc000004-0000-0000-0000-000000000001', 'bb000000-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000004', 'Psychological Assessment History (Version 1)', 'PsychAssess_1_PsychAssesHistory-Copy-2.pdf', '/Lectures - Handouts/Psychological Assessment/PsychAssess_1_PsychAssesHistory-Copy-2.pdf', 'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000004-0000-0000-0000-000000000002', 'bb000000-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000004', 'Psychological Assessment History (Version 2)', 'PsychAssess_1_PsychAssesHistory.pdf',        '/Lectures - Handouts/Psychological Assessment/PsychAssess_1_PsychAssesHistory.pdf',        'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('cc000004-0000-0000-0000-000000000003', 'bb000000-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000004', 'Psychological Assessment - Education',        'PsychAssess_7_Education.pdf',                '/Lectures - Handouts/Psychological Assessment/PsychAssess_7_Education.pdf',                'PDF', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00');


-- ================================================================
-- ASSESSMENTS
-- Per subject: 1 pre-assessment + 1 post-assessment
-- Per module:  1 quiz
-- All: 5 items, time_limit 15 min, status APPROVED
-- author = faculty assigned to that subject
-- ================================================================

INSERT INTO assessments (id, subject_id, author_id, title, type, items, time_limit, schedule, status, date_created, last_updated) VALUES

-- ── Developmental Psychology ──────────────────────────────────
-- Pre / Post
('ee000001-0000-0000-0000-000000000001', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Developmental Psychology - Pre-Assessment',  'PRE_ASSESSMENT',  5, 15, '2026-03-01 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000001-0000-0000-0000-000000000002', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Developmental Psychology - Post-Assessment', 'POST_ASSESSMENT', 5, 15, '2026-06-01 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
-- Quizzes per module
('ee000001-0000-0000-0000-000000000003', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Quiz - Prenatal',                  'QUIZ', 5, 15, '2026-03-05 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000001-0000-0000-0000-000000000004', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Quiz - Infancy',                   'QUIZ', 5, 15, '2026-03-10 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000001-0000-0000-0000-000000000005', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Quiz - Early Childhood',           'QUIZ', 5, 15, '2026-03-15 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000001-0000-0000-0000-000000000006', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Quiz - Middle and Late Childhood', 'QUIZ', 5, 15, '2026-03-20 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000001-0000-0000-0000-000000000007', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Quiz - Adolescence',               'QUIZ', 5, 15, '2026-03-25 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000001-0000-0000-0000-000000000008', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Quiz - Young Adulthood',           'QUIZ', 5, 15, '2026-04-01 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000001-0000-0000-0000-000000000009', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Quiz - Middle Adulthood',          'QUIZ', 5, 15, '2026-04-05 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000001-0000-0000-0000-000000000010', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Quiz - Old Age',                   'QUIZ', 5, 15, '2026-04-10 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000001-0000-0000-0000-000000000011', 'bb000000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Quiz - Death',                     'QUIZ', 5, 15, '2026-04-15 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Abnormal Psychology ───────────────────────────────────────
('ee000002-0000-0000-0000-000000000001', 'bb000000-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Abnormal Psychology - Pre-Assessment',  'PRE_ASSESSMENT',  5, 15, '2026-03-01 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000002-0000-0000-0000-000000000002', 'bb000000-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Abnormal Psychology - Post-Assessment', 'POST_ASSESSMENT', 5, 15, '2026-06-01 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000002-0000-0000-0000-000000000003', 'bb000000-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Quiz - Phase 1',                       'QUIZ',            5, 15, '2026-03-05 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000002-0000-0000-0000-000000000004', 'bb000000-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Quiz - Phase 2',                       'QUIZ',            5, 15, '2026-03-10 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000002-0000-0000-0000-000000000005', 'bb000000-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Quiz - Phase 3',                       'QUIZ',            5, 15, '2026-03-15 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000002-0000-0000-0000-000000000006', 'bb000000-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Quiz - Phase 4',                       'QUIZ',            5, 15, '2026-03-20 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000002-0000-0000-0000-000000000007', 'bb000000-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Quiz - Phase 5',                       'QUIZ',            5, 15, '2026-03-25 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Industrial / Organizational Psychology ───────────────────
('ee000003-0000-0000-0000-000000000001', 'bb000000-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000003', 'I/O Psychology - Pre-Assessment',        'PRE_ASSESSMENT',  5, 15, '2026-03-01 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000003-0000-0000-0000-000000000002', 'bb000000-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000003', 'I/O Psychology - Post-Assessment',       'POST_ASSESSMENT', 5, 15, '2026-06-01 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000003-0000-0000-0000-000000000003', 'bb000000-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000003', 'Quiz - Introduction to Industrial Psychology', 'QUIZ',       5, 15, '2026-03-05 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000003-0000-0000-0000-000000000004', 'bb000000-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000003', 'Quiz - Legal Issues',                  'QUIZ',            5, 15, '2026-03-10 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000003-0000-0000-0000-000000000005', 'bb000000-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000003', 'Quiz - Employee Selection',            'QUIZ',            5, 15, '2026-03-15 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Psychological Assessment ─────────────────────────────────
('ee000004-0000-0000-0000-000000000001', 'bb000000-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000004', 'Psychological Assessment - Pre-Assessment',  'PRE_ASSESSMENT',  5, 15, '2026-03-01 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000004-0000-0000-0000-000000000002', 'bb000000-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000004', 'Psychological Assessment - Post-Assessment', 'POST_ASSESSMENT', 5, 15, '2026-06-01 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000004-0000-0000-0000-000000000003', 'bb000000-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000004', 'Quiz - Assessment History (Version 1)', 'QUIZ',            5, 15, '2026-03-05 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000004-0000-0000-0000-000000000004', 'bb000000-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000004', 'Quiz - Assessment History (Version 2)', 'QUIZ',            5, 15, '2026-03-10 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ee000004-0000-0000-0000-000000000005', 'bb000000-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000004', 'Quiz - Education',                     'QUIZ',            5, 15, '2026-03-15 08:00:00', 'APPROVED', '2026-02-23 08:00:00', '2026-02-23 08:00:00');


-- ================================================================
-- QUESTIONS
-- 5 questions per assessment × 32 assessments = 160 questions
-- options: 4 choices (index 0–3), correct_answer = index of correct
-- Naming: q_<assessment_short>_<n>
-- ================================================================

INSERT INTO questions (id, author_id, text, options, correct_answer, date_created, last_updated) VALUES

-- ── DevPsy Pre-Assessment (as010000-...-001) ──────────────────
('ff010100-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Which period of development begins at conception and ends at birth?',
 '["Neonatal period","Prenatal period","Infancy","Early childhood"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010100-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000001', 'Piaget''s theory primarily focuses on which type of development?',
 '["Moral","Psychosocial","Cognitive","Physical"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010100-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000001', 'Erikson''s first psychosocial stage is best described as:',
 '["Autonomy vs. Shame","Trust vs. Mistrust","Initiative vs. Guilt","Industry vs. Inferiority"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010100-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000001', 'The cephalocaudal principle states that development proceeds:',
 '["From head to toe","From core to extremities","From simple to complex","From abstract to concrete"]', 0, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010100-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000001', 'Which theorist proposed the concept of the zone of proximal development?',
 '["Piaget","Freud","Vygotsky","Erikson"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── DevPsy Post-Assessment (as010000-...-002) ─────────────────
('ff010200-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Late adulthood is associated with which of Erikson''s stages?',
 '["Generativity vs. Stagnation","Integrity vs. Despair","Identity vs. Role Confusion","Intimacy vs. Isolation"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010200-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000001', 'Kübler-Ross''s final stage of grief is:',
 '["Bargaining","Anger","Depression","Acceptance"]', 3, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010200-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000001', 'Crystallized intelligence tends to ________ with age.',
 '["Decrease rapidly","Remain stable or increase","Disappear","Fluctuate unpredictably"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010200-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000001', 'Which attachment style is associated with consistent caregiving?',
 '["Avoidant","Disorganized","Secure","Anxious-ambivalent"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010200-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000001', 'Menopause typically occurs during which developmental stage?',
 '["Late adulthood","Early adulthood","Middle adulthood","Adolescence"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Prenatal (as010000-...-003) ────────────────────────
('ff010300-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'The germinal stage lasts approximately how many weeks after fertilization?',
 '["2 weeks","4 weeks","8 weeks","12 weeks"]', 0, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010300-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000001', 'An agent that causes birth defects is called a:',
 '["Mutagen","Pathogen","Teratogen","Allergen"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010300-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000001', 'The embryonic stage spans from week 3 to week:',
 '["6","8","10","12"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010300-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000001', 'Which layer gives rise to the nervous system?',
 '["Endoderm","Mesoderm","Ectoderm","Epiderm"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010300-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000001', 'Fetal alcohol syndrome is caused by:',
 '["Smoking","Maternal stress","Alcohol consumption during pregnancy","Poor nutrition"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Infancy (as010000-...-004) ─────────────────────────
('ff010400-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Object permanence is typically achieved by:',
 '["2 months","4 months","8 months","18 months"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010400-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000001', 'The rooting reflex helps the infant:',
 '["Grasp objects","Find the nipple for feeding","Respond to loud sounds","Maintain balance"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010400-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000001', 'Stranger anxiety typically emerges at around:',
 '["2 months","6–8 months","12 months","18 months"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010400-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000001', 'Harlow''s experiments with monkeys demonstrated the importance of:',
 '["Food provision","Contact comfort","Cognitive stimulation","Language exposure"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010400-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000001', 'Ainsworth''s Strange Situation assessed:',
 '["Motor development","Cognitive schemas","Attachment patterns","Language acquisition"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Early Childhood (as010000-...-005) ─────────────────
('ff010500-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Piaget''s preoperational stage spans ages:',
 '["0–2","2–7","7–11","11+"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010500-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000001', 'The inability to see things from another''s viewpoint is called:',
 '["Animism","Egocentrism","Centration","Irreversibility"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010500-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000001', 'Kohlberg''s preconventional level of moral reasoning is driven by:',
 '["Social norms","Personal principles","Rewards and punishments","Empathy"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010500-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000001', 'Gender constancy refers to understanding that:',
 '["Gender is determined by chromosomes","Gender does not change over time","Gender is a social construct","Gender changes with appearance"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010500-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000001', 'Which parenting style combines high warmth with high control?',
 '["Authoritarian","Permissive","Uninvolved","Authoritative"]', 3, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Middle and Late Childhood (as010000-...-006) ───────
('ff010600-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Conservation tasks are mastered during Piaget''s ________ stage.',
 '["Sensorimotor","Preoperational","Concrete operational","Formal operational"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010600-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000001', 'Industry vs. Inferiority is the psychosocial crisis of:',
 '["Early childhood","Middle childhood","Adolescence","Young adulthood"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010600-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000001', 'A child''s increasing ability to consider multiple dimensions is called:',
 '["Decentration","Egocentrism","Animism","Seriation"]', 0, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010600-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000001', 'Metacognition refers to:',
 '["Learning by observation","Thinking about one''s own thinking","Emotional regulation","Moral reasoning"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010600-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000001', 'Peer rejection in middle childhood is most associated with:',
 '["Academic achievement","Secure attachment","Aggressive or withdrawn behavior","High creativity"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Adolescence (as010000-...-007) ─────────────────────
('ff010700-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Erikson''s stage for adolescence involves:',
 '["Trust vs. Mistrust","Identity vs. Role Confusion","Intimacy vs. Isolation","Industry vs. Inferiority"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010700-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000001', 'The imaginary audience phenomenon reflects:',
 '["Altruism","Heightened self-consciousness","Decreased egocentrism","Moral development"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010700-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000001', 'Formal operational thinking allows adolescents to:',
 '["Think concretely","Use symbols","Reason abstractly and hypothetically","Perform conservation tasks"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010700-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000001', 'James Marcia''s identity achievement status involves:',
 '["No exploration or commitment","Commitment without exploration","Exploration without commitment","Exploration followed by commitment"]', 3, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010700-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000001', 'The primary sex characteristic in females is:',
 '["Breast development","Ovaries","Pubic hair","Widening hips"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Young Adulthood (as010000-...-008) ─────────────────
('ff010800-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Erikson''s stage for young adulthood is:',
 '["Generativity vs. Stagnation","Identity vs. Role Confusion","Intimacy vs. Isolation","Integrity vs. Despair"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010800-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000001', 'Sternberg''s triangular theory of love includes all EXCEPT:',
 '["Passion","Commitment","Intimacy","Empathy"]', 3, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010800-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000001', 'Fluid intelligence peaks during:',
 '["Childhood","Young adulthood","Middle adulthood","Late adulthood"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010800-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000001', 'The term "emerging adulthood" was coined by:',
 '["Erikson","Arnett","Levinson","Havighurst"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010800-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000001', 'Levinson described early adulthood as the "novice phase" because:',
 '["People are inexperienced workers","Adults are forming initial life structures","Young adults lack identity","Adults peak cognitively"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Middle Adulthood (as010000-...-009) ────────────────
('ff010900-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Generativity vs. Stagnation is Erikson''s stage for:',
 '["Late adulthood","Young adulthood","Middle adulthood","Adolescence"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010900-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000001', 'The "midlife crisis" concept was introduced by:',
 '["Erikson","Levinson","Vaillant","Jung"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010900-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000001', 'Which type of intelligence increases during middle adulthood?',
 '["Fluid intelligence","Crystallized intelligence","Spatial intelligence","Processing speed"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010900-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000001', 'The "empty nest syndrome" refers to:',
 '["Cognitive decline","Retirement stress","Distress when children leave home","Loss of spouse"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff010900-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000001', 'Sandwich generation refers to adults who:',
 '["Care for both aging parents and own children","Experience identity confusion","Are between jobs","Transition to retirement"]', 0, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Old Age (as010000-...-010) ─────────────────────────
('ff011000-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'Alzheimer''s disease primarily affects:',
 '["Motor function","Memory and cognitive function","Emotional regulation","Language production"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff011000-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000001', 'Successful aging theory emphasizes:',
 '["Complete withdrawal from society","Low activity and disengagement","High activity and social engagement","Accepting physical decline"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff011000-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000001', 'Integrity vs. Despair is resolved through:',
 '["Future goal setting","Reflection on a meaningful life","Social withdrawal","Denial of death"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff011000-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000001', 'Which cognitive ability shows the least decline in late adulthood?',
 '["Processing speed","Working memory","Vocabulary and semantic memory","Divided attention"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff011000-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000001', 'The disengagement theory suggests that aging involves:',
 '["Staying active","Mutual withdrawal from society","Selective engagement","Continuous development"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Death (as010000-...-011) ───────────────────────────
('ff011100-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000001', 'The first stage of Kübler-Ross''s grief model is:',
 '["Anger","Denial","Bargaining","Depression"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff011100-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000001', 'Palliative care focuses primarily on:',
 '["Curing terminal illness","Prolonging life at all costs","Comfort and quality of life","Surgical intervention"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff011100-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000001', 'Bereavement refers to:',
 '["The process of dying","The state of having lost someone","Fear of death","Care for the dying"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff011100-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000001', 'Terror management theory proposes that culture serves as:',
 '["A source of economic stability","A buffer against death anxiety","A guide for moral behavior","A means of social control"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff011100-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000001', 'A "good death" is commonly characterized by:',
 '["Sudden unexpected death","Pain management and dignity","Dying alone","Dying young"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Abnormal Pre-Assessment (as020000-...-001) ────────────────
('ff020100-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000002', 'The DSM-5 is primarily used for:',
 '["Measuring intelligence","Diagnosing mental disorders","Assessing personality","Evaluating neurological function"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020100-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'The biopsychosocial model considers mental illness as a product of:',
 '["Only biological factors","Only psychological factors","Biological, psychological, and social factors","Social factors alone"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020100-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000002', 'The "4 Ds" used to define abnormal behavior include distress, deviance, dysfunction, and:',
 '["Delusion","Danger","Disorder","Depression"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020100-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000002', 'Comorbidity means a person:',
 '["Has a severe mental illness","Has two or more disorders simultaneously","Recovers from mental illness","Shows resistance to treatment"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020100-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000002', 'The medical model of abnormality views mental disorders as:',
 '["Learned behaviors","Social constructs","Diseases with biological bases","Moral failures"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Abnormal Post-Assessment (as020000-...-002) ───────────────
('ff020200-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000002', 'CBT is most effective for treating:',
 '["Schizophrenia","Anxiety and mood disorders","Personality disorders","Substance dependence"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020200-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Positive symptoms of schizophrenia include:',
 '["Flat affect","Alogia","Hallucinations","Social withdrawal"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020200-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000002', 'Which disorder is characterized by persistent low mood for at least 2 years?',
 '["Major depressive disorder","Bipolar I","Dysthymia (Persistent Depressive Disorder)","Cyclothymia"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020200-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000002', 'The hallmark of OCD is:',
 '["Delusions","Obsessions and compulsions","Phobias","Dissociation"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020200-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000002', 'Borderline personality disorder is primarily characterized by:',
 '["Grandiosity","Instability in mood, identity, and relationships","Social detachment","Chronic lying"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Abnormal Phase 1 (as020000-...-003) ────────────────
('ff020300-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000002', 'Which historical treatment involved drilling holes in the skull?',
 '["Lobotomy","Electroconvulsive therapy","Trephination","Hydrotherapy"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020300-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'The demonological model attributed mental illness to:',
 '["Brain lesions","Evil spirits","Social stress","Genetic defects"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020300-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000002', 'Philippe Pinel is known for:',
 '["Inventing the DSM","Advocating humane treatment of the mentally ill","Developing CBT","Discovering antipsychotic drugs"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020300-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000002', 'Which approach sees abnormal behavior as a result of learned responses?',
 '["Biological","Psychodynamic","Behavioral","Humanistic"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020300-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000002', 'The statistical definition of abnormality defines it as:',
 '["Behavior that causes harm","Behavior deviating far from the average","Behavior that violates social norms","Behavior that leads to distress"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Abnormal Phase 2 (as020000-...-004) ────────────────
('ff020400-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000002', 'Major depressive disorder requires symptoms for at least:',
 '["1 week","2 weeks","1 month","6 months"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020400-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Bipolar I disorder is distinguished from Bipolar II by:',
 '["Hypomanic episodes","Full manic episodes","Depressive episodes only","Mixed episodes only"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020400-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000002', 'Anhedonia refers to:',
 '["Excessive fear","Inability to experience pleasure","Memory loss","Hallucinations"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020400-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000002', 'Learned helplessness is linked to the development of:',
 '["Schizophrenia","Anxiety disorders","Depression","Personality disorders"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020400-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000002', 'SSRIs are primarily used to treat:',
 '["Schizophrenia","Depression and anxiety","ADHD","Bipolar disorder"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Abnormal Phase 3 (as020000-...-005) ────────────────
('ff020500-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000002', 'Generalized anxiety disorder is characterized by:',
 '["Specific phobias","Panic attacks","Excessive worry about multiple life areas","Obsessive thoughts"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020500-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'PTSD develops following:',
 '["A stressful job","Exposure to traumatic events","Social isolation","Childhood neglect only"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020500-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000002', 'The core feature of panic disorder is:',
 '["Chronic worry","Recurrent unexpected panic attacks","Social avoidance","Intrusive memories"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020500-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000002', 'Agoraphobia involves fear of:',
 '["Heights","Open or public spaces","Spiders","Social situations"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020500-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000002', 'EMDR is a treatment primarily used for:',
 '["Schizophrenia","PTSD","Bipolar disorder","Eating disorders"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Abnormal Phase 4 (as020000-...-006) ────────────────
('ff020600-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000002', 'The hallmark symptom of schizophrenia is:',
 '["Mood swings","Psychosis","Compulsions","Dissociation"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020600-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Negative symptoms of schizophrenia include:',
 '["Hallucinations","Delusions","Flat affect and alogia","Disorganized speech"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020600-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000002', 'The dopamine hypothesis of schizophrenia suggests:',
 '["Excess serotonin","Excess dopamine activity","Low GABA","Low norepinephrine"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020600-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000002', 'Schizoaffective disorder combines features of schizophrenia and:',
 '["Personality disorder","Anxiety disorder","Mood disorder","Substance use disorder"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020600-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000002', 'First-generation antipsychotics primarily block:',
 '["Serotonin receptors","Dopamine D2 receptors","GABA receptors","Glutamate receptors"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Abnormal Phase 5 (as020000-...-007) ────────────────
('ff020700-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000002', 'Anorexia nervosa is characterized by:',
 '["Binge eating","Severe food restriction and distorted body image","Normal weight with purging","Compulsive overeating"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020700-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000002', 'Antisocial personality disorder involves a pervasive pattern of:',
 '["Social anxiety","Disregard for others'' rights","Emotional dependency","Paranoid thinking"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020700-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000002', 'Substance use disorder is diagnosed based on:',
 '["Frequency of use alone","Amount used","Impaired control and negative consequences","Withdrawal symptoms only"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020700-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000002', 'Dialectical behavior therapy (DBT) was developed for:',
 '["Schizophrenia","Borderline personality disorder","ADHD","Autism spectrum disorder"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff020700-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000002', 'Which disorder involves alternating identities?',
 '["Depersonalization disorder","Dissociative amnesia","Dissociative identity disorder","Derealization disorder"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── I/O Pre-Assessment (as030000-...-001) ─────────────────────
('ff030100-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000003', 'I/O psychology applies psychological principles to:',
 '["Clinical settings","Educational institutions","The workplace","Community health"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030100-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000003', 'The Hawthorne effect refers to:',
 '["Increased productivity from better lighting","Behavior change due to being observed","Reduced morale from monotony","Enhanced creativity in teams"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030100-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000003', 'Job analysis is the process of:',
 '["Evaluating employee performance","Identifying job duties and requirements","Designing compensation packages","Measuring job satisfaction"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030100-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000003', 'Organizational culture refers to:',
 '["Formal company policies","Shared values and norms in an organization","Management hierarchy","Employee benefits"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030100-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000003', 'Which motivation theory distinguishes hygiene factors from motivators?',
 '["Maslow''s hierarchy","McClelland''s needs theory","Herzberg''s two-factor theory","Vroom''s expectancy theory"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── I/O Post-Assessment (as030000-...-002) ────────────────────
('ff030200-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000003', 'Organizational commitment refers to:',
 '["Following rules strictly","Employee''s emotional attachment to their organization","Time spent at work","Meeting deadlines"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030200-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000003', 'Which leadership style involves sharing decision-making with employees?',
 '["Autocratic","Laissez-faire","Transactional","Participative"]', 3, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030200-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000003', 'Work-life balance interventions primarily aim to reduce:',
 '["Productivity","Absenteeism and burnout","Employee training costs","Organizational hierarchy"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030200-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000003', '360-degree feedback collects input from:',
 '["Direct supervisor only","HR department","Multiple sources including peers and subordinates","Customers only"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030200-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000003', 'Occupational stress is best managed through:',
 '["Ignoring stressors","Increased work hours","Coping strategies and organizational support","Social isolation"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Intro to Industrial Psychology (as030000-...-003) ──
('ff030300-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000003', 'Hugo Münsterberg is considered a founder of:',
 '["Clinical psychology","Industrial psychology","School psychology","Neuropsychology"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030300-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000003', 'Scientific management was developed by:',
 '["Elton Mayo","Frederick Taylor","Max Weber","Abraham Maslow"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030300-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000003', 'Which of the following is NOT a subfield of I/O psychology?',
 '["Personnel psychology","Organizational psychology","Forensic psychology","Human factors"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030300-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000003', 'The primary goal of personnel psychology is:',
 '["Team building","Selecting and evaluating employees","Reducing workplace conflict","Designing office spaces"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030300-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000003', 'The Hawthorne studies were conducted at:',
 '["General Motors","Western Electric Company","Ford Motors","IBM"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Legal Issues (as030000-...-004) ────────────────────
('ff030400-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000003', 'Title VII of the Civil Rights Act prohibits discrimination based on:',
 '["Age","Disability","Race, color, religion, sex, and national origin","Salary"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030400-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000003', 'Adverse impact occurs when a selection procedure:',
 '["Favors all candidates equally","Disproportionately screens out a protected group","Increases diversity","Passes all applicants"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030400-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000003', 'The 4/5ths rule is used to detect:',
 '["Wage gaps","Adverse impact in selection","Age discrimination","Harassment"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030400-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000003', 'Quid pro quo harassment involves:',
 '["A hostile work environment","Job benefits tied to sexual favors","Verbal abuse","Unequal pay"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030400-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000003', 'Reasonable accommodation under the ADA means:',
 '["Removing all physical barriers","Modifications that enable a qualified employee with a disability to work","Hiring quotas","Free medical care"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - Employee Selection (as030000-...-005) ──────────────
('ff030500-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000003', 'Criterion validity measures how well a test predicts:',
 '["Cultural fit","Job performance","Intelligence","Personality traits"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030500-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000003', 'A structured interview differs from an unstructured one by:',
 '["Being longer","Using identical questions for all candidates","Focusing on personality","Being conducted by multiple interviewers"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030500-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000003', 'Assessment centers evaluate candidates using:',
 '["Written tests only","Multiple exercises simulating job tasks","Personality questionnaires alone","Background checks"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030500-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000003', 'Which selection method has the highest predictive validity for job performance?',
 '["Unstructured interview","Reference checks","Work sample tests","Graphology"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff030500-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000003', 'Reliability in a selection test refers to:',
 '["Measuring the right construct","Consistency of scores across time and conditions","Legal compliance","Cost-effectiveness"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── PA Pre-Assessment (as040000-...-001) ──────────────────────
('ff040100-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000004', 'Psychological assessment is best defined as:',
 '["Administering a single test","A systematic process of gathering and evaluating psychological data","Diagnosing mental illness","Measuring IQ only"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040100-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000004', 'Reliability in psychological testing refers to:',
 '["The test measures what it claims to","Consistent results across administrations","Normative comparisons","Cultural fairness"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040100-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000004', 'Validity refers to whether a test:',
 '["Produces consistent results","Measures what it is supposed to measure","Is easy to administer","Has norms"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040100-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000004', 'A norm-referenced test compares a test-taker to:',
 '["A fixed standard","A criterion","A normative sample","The test-taker''s previous scores"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040100-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000004', 'The standard error of measurement reflects:',
 '["Test bias","The expected variability in scores due to measurement error","The range of normed scores","Cultural differences"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── PA Post-Assessment (as040000-...-002) ─────────────────────
('ff040200-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000004', 'A psychological report should always include:',
 '["A diagnosis","Referral question, results, interpretation, and recommendations","Raw scores only","Clinician''s personal opinion"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040200-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000004', 'Projective tests are based on the assumption that:',
 '["Intelligence is measurable","People project unconscious material onto ambiguous stimuli","Behavior predicts performance","Responses are objective"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040200-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000004', 'The MMPI is primarily used to assess:',
 '["Intelligence","Personality and psychopathology","Academic achievement","Neurological function"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040200-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000004', 'Test bias exists when a test:',
 '["Has low reliability","Produces systematically different results for different groups unfairly","Is too long","Has no normative data"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040200-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000004', 'Informed consent in assessment means the client:',
 '["Signs a waiver","Understands the purpose and nature of the assessment","Waives the right to results","Agrees to all recommendations"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - PA History v1 (as040000-...-003) ───────────────────
('ff040300-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000004', 'The first formal intelligence test was developed by:',
 '["Wundt","Galton","Binet and Simon","Terman"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040300-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000004', 'The Army Alpha and Beta tests were developed for:',
 '["Educational placement","Clinical diagnosis","Military recruitment in WWI","Vocational guidance"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040300-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000004', 'Francis Galton''s contribution to psychology included:',
 '["Developing psychotherapy","Studying individual differences and mental testing","Creating the DSM","Founding behaviorism"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040300-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000004', 'The concept of mental age was introduced by:',
 '["Galton","Cattell","Binet","Terman"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040300-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000004', 'The IQ formula (MA/CA × 100) was devised by:',
 '["Binet","Stern","Terman","Wechsler"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - PA History v2 (as040000-...-004) ───────────────────
('ff040400-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000004', 'The Wechsler scales differ from the Stanford-Binet by providing:',
 '["A single global IQ","Deviation IQ and index scores","Faster administration","Age-equivalent scores only"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040400-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000004', 'The Minnesota Multiphasic Personality Inventory (MMPI) was developed in:',
 '["1920s","1930s","1940s","1950s"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040400-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000004', 'The Rorschach Inkblot Test was published in:',
 '["1905","1921","1935","1949"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040400-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000004', 'The movement toward evidence-based assessment emphasizes:',
 '["Intuitive clinical judgment","Using only projective tests","Tests with demonstrated reliability and validity","Minimal documentation"]', 2, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040400-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000004', 'Computerized adaptive testing adjusts difficulty based on:',
 '["Time remaining","The examinee''s previous responses","Random selection","Examiner preference"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),

-- ── Quiz - PA Education (as040000-...-005) ────────────────────
('ff040500-0000-0000-0000-000000000001', '00000000-0000-0000-0002-000000000004', 'An IEP (Individualized Education Program) is designed for:',
 '["Gifted students only","Students with disabilities","All students","Students with behavioral issues only"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040500-0000-0000-0000-000000000002', '00000000-0000-0000-0002-000000000004', 'Curriculum-based measurement (CBM) assesses:',
 '["Intelligence","A student''s performance within the school curriculum","Personality","Neurological function"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040500-0000-0000-0000-000000000003', '00000000-0000-0000-0002-000000000004', 'Specific learning disability is characterized by:',
 '["Low overall IQ","Significant deficit in one academic area despite adequate intelligence","Global developmental delay","Behavioral disorder"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040500-0000-0000-0000-000000000004', '00000000-0000-0000-0002-000000000004', 'Dynamic assessment focuses on:',
 '["What a student currently knows","A student''s potential to learn with guided support","Standardized test performance","Academic history"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00'),
('ff040500-0000-0000-0000-000000000005', '00000000-0000-0000-0002-000000000004', 'Response to Intervention (RTI) is used to:',
 '["Replace IQ testing","Identify and support students at risk early","Diagnose ADHD","Assess gifted students"]', 1, '2026-02-23 08:00:00', '2026-02-23 08:00:00');


-- ================================================================
-- ASSESSMENT_QUESTIONS  (link each assessment to its 5 questions)
-- ================================================================

INSERT INTO assessment_questions (assessment_id, question_id) VALUES
-- DevPsy Pre
('ee000001-0000-0000-0000-000000000001','ff010100-0000-0000-0000-000000000001'),
('ee000001-0000-0000-0000-000000000001','ff010100-0000-0000-0000-000000000002'),
('ee000001-0000-0000-0000-000000000001','ff010100-0000-0000-0000-000000000003'),
('ee000001-0000-0000-0000-000000000001','ff010100-0000-0000-0000-000000000004'),
('ee000001-0000-0000-0000-000000000001','ff010100-0000-0000-0000-000000000005'),
-- DevPsy Post
('ee000001-0000-0000-0000-000000000002','ff010200-0000-0000-0000-000000000001'),
('ee000001-0000-0000-0000-000000000002','ff010200-0000-0000-0000-000000000002'),
('ee000001-0000-0000-0000-000000000002','ff010200-0000-0000-0000-000000000003'),
('ee000001-0000-0000-0000-000000000002','ff010200-0000-0000-0000-000000000004'),
('ee000001-0000-0000-0000-000000000002','ff010200-0000-0000-0000-000000000005'),
-- Quiz Prenatal
('ee000001-0000-0000-0000-000000000003','ff010300-0000-0000-0000-000000000001'),
('ee000001-0000-0000-0000-000000000003','ff010300-0000-0000-0000-000000000002'),
('ee000001-0000-0000-0000-000000000003','ff010300-0000-0000-0000-000000000003'),
('ee000001-0000-0000-0000-000000000003','ff010300-0000-0000-0000-000000000004'),
('ee000001-0000-0000-0000-000000000003','ff010300-0000-0000-0000-000000000005'),
-- Quiz Infancy
('ee000001-0000-0000-0000-000000000004','ff010400-0000-0000-0000-000000000001'),
('ee000001-0000-0000-0000-000000000004','ff010400-0000-0000-0000-000000000002'),
('ee000001-0000-0000-0000-000000000004','ff010400-0000-0000-0000-000000000003'),
('ee000001-0000-0000-0000-000000000004','ff010400-0000-0000-0000-000000000004'),
('ee000001-0000-0000-0000-000000000004','ff010400-0000-0000-0000-000000000005'),
-- Quiz Early Childhood
('ee000001-0000-0000-0000-000000000005','ff010500-0000-0000-0000-000000000001'),
('ee000001-0000-0000-0000-000000000005','ff010500-0000-0000-0000-000000000002'),
('ee000001-0000-0000-0000-000000000005','ff010500-0000-0000-0000-000000000003'),
('ee000001-0000-0000-0000-000000000005','ff010500-0000-0000-0000-000000000004'),
('ee000001-0000-0000-0000-000000000005','ff010500-0000-0000-0000-000000000005'),
-- Quiz Middle & Late Childhood
('ee000001-0000-0000-0000-000000000006','ff010600-0000-0000-0000-000000000001'),
('ee000001-0000-0000-0000-000000000006','ff010600-0000-0000-0000-000000000002'),
('ee000001-0000-0000-0000-000000000006','ff010600-0000-0000-0000-000000000003'),
('ee000001-0000-0000-0000-000000000006','ff010600-0000-0000-0000-000000000004'),
('ee000001-0000-0000-0000-000000000006','ff010600-0000-0000-0000-000000000005'),
-- Quiz Adolescence
('ee000001-0000-0000-0000-000000000007','ff010700-0000-0000-0000-000000000001'),
('ee000001-0000-0000-0000-000000000007','ff010700-0000-0000-0000-000000000002'),
('ee000001-0000-0000-0000-000000000007','ff010700-0000-0000-0000-000000000003'),
('ee000001-0000-0000-0000-000000000007','ff010700-0000-0000-0000-000000000004'),
('ee000001-0000-0000-0000-000000000007','ff010700-0000-0000-0000-000000000005'),
-- Quiz Young Adulthood
('ee000001-0000-0000-0000-000000000008','ff010800-0000-0000-0000-000000000001'),
('ee000001-0000-0000-0000-000000000008','ff010800-0000-0000-0000-000000000002'),
('ee000001-0000-0000-0000-000000000008','ff010800-0000-0000-0000-000000000003'),
('ee000001-0000-0000-0000-000000000008','ff010800-0000-0000-0000-000000000004'),
('ee000001-0000-0000-0000-000000000008','ff010800-0000-0000-0000-000000000005'),
-- Quiz Middle Adulthood
('ee000001-0000-0000-0000-000000000009','ff010900-0000-0000-0000-000000000001'),
('ee000001-0000-0000-0000-000000000009','ff010900-0000-0000-0000-000000000002'),
('ee000001-0000-0000-0000-000000000009','ff010900-0000-0000-0000-000000000003'),
('ee000001-0000-0000-0000-000000000009','ff010900-0000-0000-0000-000000000004'),
('ee000001-0000-0000-0000-000000000009','ff010900-0000-0000-0000-000000000005'),
-- Quiz Old Age
('ee000001-0000-0000-0000-000000000010','ff011000-0000-0000-0000-000000000001'),
('ee000001-0000-0000-0000-000000000010','ff011000-0000-0000-0000-000000000002'),
('ee000001-0000-0000-0000-000000000010','ff011000-0000-0000-0000-000000000003'),
('ee000001-0000-0000-0000-000000000010','ff011000-0000-0000-0000-000000000004'),
('ee000001-0000-0000-0000-000000000010','ff011000-0000-0000-0000-000000000005'),
-- Quiz Death
('ee000001-0000-0000-0000-000000000011','ff011100-0000-0000-0000-000000000001'),
('ee000001-0000-0000-0000-000000000011','ff011100-0000-0000-0000-000000000002'),
('ee000001-0000-0000-0000-000000000011','ff011100-0000-0000-0000-000000000003'),
('ee000001-0000-0000-0000-000000000011','ff011100-0000-0000-0000-000000000004'),
('ee000001-0000-0000-0000-000000000011','ff011100-0000-0000-0000-000000000005'),
-- AbPsy Pre
('ee000002-0000-0000-0000-000000000001','ff020100-0000-0000-0000-000000000001'),
('ee000002-0000-0000-0000-000000000001','ff020100-0000-0000-0000-000000000002'),
('ee000002-0000-0000-0000-000000000001','ff020100-0000-0000-0000-000000000003'),
('ee000002-0000-0000-0000-000000000001','ff020100-0000-0000-0000-000000000004'),
('ee000002-0000-0000-0000-000000000001','ff020100-0000-0000-0000-000000000005'),
-- AbPsy Post
('ee000002-0000-0000-0000-000000000002','ff020200-0000-0000-0000-000000000001'),
('ee000002-0000-0000-0000-000000000002','ff020200-0000-0000-0000-000000000002'),
('ee000002-0000-0000-0000-000000000002','ff020200-0000-0000-0000-000000000003'),
('ee000002-0000-0000-0000-000000000002','ff020200-0000-0000-0000-000000000004'),
('ee000002-0000-0000-0000-000000000002','ff020200-0000-0000-0000-000000000005'),
-- Quiz Phase 1
('ee000002-0000-0000-0000-000000000003','ff020300-0000-0000-0000-000000000001'),
('ee000002-0000-0000-0000-000000000003','ff020300-0000-0000-0000-000000000002'),
('ee000002-0000-0000-0000-000000000003','ff020300-0000-0000-0000-000000000003'),
('ee000002-0000-0000-0000-000000000003','ff020300-0000-0000-0000-000000000004'),
('ee000002-0000-0000-0000-000000000003','ff020300-0000-0000-0000-000000000005'),
-- Quiz Phase 2
('ee000002-0000-0000-0000-000000000004','ff020400-0000-0000-0000-000000000001'),
('ee000002-0000-0000-0000-000000000004','ff020400-0000-0000-0000-000000000002'),
('ee000002-0000-0000-0000-000000000004','ff020400-0000-0000-0000-000000000003'),
('ee000002-0000-0000-0000-000000000004','ff020400-0000-0000-0000-000000000004'),
('ee000002-0000-0000-0000-000000000004','ff020400-0000-0000-0000-000000000005'),
-- Quiz Phase 3
('ee000002-0000-0000-0000-000000000005','ff020500-0000-0000-0000-000000000001'),
('ee000002-0000-0000-0000-000000000005','ff020500-0000-0000-0000-000000000002'),
('ee000002-0000-0000-0000-000000000005','ff020500-0000-0000-0000-000000000003'),
('ee000002-0000-0000-0000-000000000005','ff020500-0000-0000-0000-000000000004'),
('ee000002-0000-0000-0000-000000000005','ff020500-0000-0000-0000-000000000005'),
-- Quiz Phase 4
('ee000002-0000-0000-0000-000000000006','ff020600-0000-0000-0000-000000000001'),
('ee000002-0000-0000-0000-000000000006','ff020600-0000-0000-0000-000000000002'),
('ee000002-0000-0000-0000-000000000006','ff020600-0000-0000-0000-000000000003'),
('ee000002-0000-0000-0000-000000000006','ff020600-0000-0000-0000-000000000004'),
('ee000002-0000-0000-0000-000000000006','ff020600-0000-0000-0000-000000000005'),
-- Quiz Phase 5
('ee000002-0000-0000-0000-000000000007','ff020700-0000-0000-0000-000000000001'),
('ee000002-0000-0000-0000-000000000007','ff020700-0000-0000-0000-000000000002'),
('ee000002-0000-0000-0000-000000000007','ff020700-0000-0000-0000-000000000003'),
('ee000002-0000-0000-0000-000000000007','ff020700-0000-0000-0000-000000000004'),
('ee000002-0000-0000-0000-000000000007','ff020700-0000-0000-0000-000000000005'),
-- I/O Pre
('ee000003-0000-0000-0000-000000000001','ff030100-0000-0000-0000-000000000001'),
('ee000003-0000-0000-0000-000000000001','ff030100-0000-0000-0000-000000000002'),
('ee000003-0000-0000-0000-000000000001','ff030100-0000-0000-0000-000000000003'),
('ee000003-0000-0000-0000-000000000001','ff030100-0000-0000-0000-000000000004'),
('ee000003-0000-0000-0000-000000000001','ff030100-0000-0000-0000-000000000005'),
-- I/O Post
('ee000003-0000-0000-0000-000000000002','ff030200-0000-0000-0000-000000000001'),
('ee000003-0000-0000-0000-000000000002','ff030200-0000-0000-0000-000000000002'),
('ee000003-0000-0000-0000-000000000002','ff030200-0000-0000-0000-000000000003'),
('ee000003-0000-0000-0000-000000000002','ff030200-0000-0000-0000-000000000004'),
('ee000003-0000-0000-0000-000000000002','ff030200-0000-0000-0000-000000000005'),
-- Quiz Intro to I/O
('ee000003-0000-0000-0000-000000000003','ff030300-0000-0000-0000-000000000001'),
('ee000003-0000-0000-0000-000000000003','ff030300-0000-0000-0000-000000000002'),
('ee000003-0000-0000-0000-000000000003','ff030300-0000-0000-0000-000000000003'),
('ee000003-0000-0000-0000-000000000003','ff030300-0000-0000-0000-000000000004'),
('ee000003-0000-0000-0000-000000000003','ff030300-0000-0000-0000-000000000005'),
-- Quiz Legal Issues
('ee000003-0000-0000-0000-000000000004','ff030400-0000-0000-0000-000000000001'),
('ee000003-0000-0000-0000-000000000004','ff030400-0000-0000-0000-000000000002'),
('ee000003-0000-0000-0000-000000000004','ff030400-0000-0000-0000-000000000003'),
('ee000003-0000-0000-0000-000000000004','ff030400-0000-0000-0000-000000000004'),
('ee000003-0000-0000-0000-000000000004','ff030400-0000-0000-0000-000000000005'),
-- Quiz Employee Selection
('ee000003-0000-0000-0000-000000000005','ff030500-0000-0000-0000-000000000001'),
('ee000003-0000-0000-0000-000000000005','ff030500-0000-0000-0000-000000000002'),
('ee000003-0000-0000-0000-000000000005','ff030500-0000-0000-0000-000000000003'),
('ee000003-0000-0000-0000-000000000005','ff030500-0000-0000-0000-000000000004'),
('ee000003-0000-0000-0000-000000000005','ff030500-0000-0000-0000-000000000005'),
-- PA Pre
('ee000004-0000-0000-0000-000000000001','ff040100-0000-0000-0000-000000000001'),
('ee000004-0000-0000-0000-000000000001','ff040100-0000-0000-0000-000000000002'),
('ee000004-0000-0000-0000-000000000001','ff040100-0000-0000-0000-000000000003'),
('ee000004-0000-0000-0000-000000000001','ff040100-0000-0000-0000-000000000004'),
('ee000004-0000-0000-0000-000000000001','ff040100-0000-0000-0000-000000000005'),
-- PA Post
('ee000004-0000-0000-0000-000000000002','ff040200-0000-0000-0000-000000000001'),
('ee000004-0000-0000-0000-000000000002','ff040200-0000-0000-0000-000000000002'),
('ee000004-0000-0000-0000-000000000002','ff040200-0000-0000-0000-000000000003'),
('ee000004-0000-0000-0000-000000000002','ff040200-0000-0000-0000-000000000004'),
('ee000004-0000-0000-0000-000000000002','ff040200-0000-0000-0000-000000000005'),
-- Quiz PA History v1
('ee000004-0000-0000-0000-000000000003','ff040300-0000-0000-0000-000000000001'),
('ee000004-0000-0000-0000-000000000003','ff040300-0000-0000-0000-000000000002'),
('ee000004-0000-0000-0000-000000000003','ff040300-0000-0000-0000-000000000003'),
('ee000004-0000-0000-0000-000000000003','ff040300-0000-0000-0000-000000000004'),
('ee000004-0000-0000-0000-000000000003','ff040300-0000-0000-0000-000000000005'),
-- Quiz PA History v2
('ee000004-0000-0000-0000-000000000004','ff040400-0000-0000-0000-000000000001'),
('ee000004-0000-0000-0000-000000000004','ff040400-0000-0000-0000-000000000002'),
('ee000004-0000-0000-0000-000000000004','ff040400-0000-0000-0000-000000000003'),
('ee000004-0000-0000-0000-000000000004','ff040400-0000-0000-0000-000000000004'),
('ee000004-0000-0000-0000-000000000004','ff040400-0000-0000-0000-000000000005'),
-- Quiz Education
('ee000004-0000-0000-0000-000000000005','ff040500-0000-0000-0000-000000000001'),
('ee000004-0000-0000-0000-000000000005','ff040500-0000-0000-0000-000000000002'),
('ee000004-0000-0000-0000-000000000005','ff040500-0000-0000-0000-000000000003'),
('ee000004-0000-0000-0000-000000000005','ff040500-0000-0000-0000-000000000004'),
('ee000004-0000-0000-0000-000000000005','ff040500-0000-0000-0000-000000000005');


-- ================================================================
-- SEED SUMMARY
-- Roles:        3  (ADMIN, FACULTY, STUDENT)
-- Users:        20 (3 admin, 5 faculty, 12 student)
-- Subjects:     4
-- Modules:      20 (9 DevPsy, 5 AbPsy, 3 I/O, 3 PA)
-- Assessments:  32 (8 pre/post + 24 quizzes)
-- Questions:   160 (5 per assessment)
-- ================================================================