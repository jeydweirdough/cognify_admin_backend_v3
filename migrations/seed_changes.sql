-- ============================================================
-- seed.sql — Initial Dataset (Aligned with updated schema)
-- Run AFTER schema_changes.sql
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
-- ────────────────────────────────────────────────────────────
INSERT INTO roles (id, name, permissions, is_system, created_at) VALUES
    ('00000000-0000-0000-0000-000000000001', 'ADMIN',
        '["manage_users","manage_content","manage_assessments","manage_subjects","manage_settings","view_analytics","approve_content","manage_roles"]',
        TRUE, NOW()),
    ('00000000-0000-0000-0000-000000000002', 'FACULTY',
        '["create_content","submit_content","create_assessments","submit_assessments","view_analytics","view_subjects"]',
        TRUE, NOW()),
    ('00000000-0000-0000-0000-000000000003', 'STUDENT',
        '["view_content","take_assessments","view_progress","view_subjects"]',
        TRUE, NOW())
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 3. USERS
-- Notice: Using 'cvsu_id' instead of institutional_id
-- ────────────────────────────────────────────────────────────
INSERT INTO users (
    id, cvsu_id, first_name, middle_name, last_name,
    email, password, role_id, status, department, date_created
) VALUES
('10000000-0000-0000-0000-000000000001', 'ADMIN-001', 'Ana', 'Cruz', 'Reyes', 'admin@cvsu.edu.ph',
 '$2b$12$KIXbhELtNrGF7JK7CzIxiONH5V7M3G0GzGPHMK5JxGmE0s0P2yOZC', '00000000-0000-0000-0000-000000000001', 'ACTIVE', 'Administration', NOW() - INTERVAL '180 days'),

('10000000-0000-0000-0000-000000000002', 'FAC-2024-001', 'Marco', 'Antonio', 'Santos', 'faculty1@cvsu.edu.ph',
 '$2b$12$X8RhYvBn7MtK3O4P5qAh8eP2Z3KMQd9hW1aJlH4yNxVRmUxS1sOaC', '00000000-0000-0000-0000-000000000002', 'ACTIVE', 'Developmental Psychology', NOW() - INTERVAL '150 days'),

('10000000-0000-0000-0000-000000000003', 'FAC-2024-002', 'Elena', 'Grace', 'Villanueva', 'faculty2@cvsu.edu.ph',
 '$2b$12$X8RhYvBn7MtK3O4P5qAh8eP2Z3KMQd9hW1aJlH4yNxVRmUxS1sOaC', '00000000-0000-0000-0000-000000000002', 'ACTIVE', 'Clinical Psychology', NOW() - INTERVAL '120 days'),

('10000000-0000-0000-0000-000000000011', '2024-PSY-001', 'Jose', 'Miguel', 'Garcia', 'student1@cvsu.edu.ph',
 '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6', '00000000-0000-0000-0000-000000000003', 'ACTIVE', 'BS Psychology', NOW() - INTERVAL '90 days'),

('10000000-0000-0000-0000-000000000012', '2024-PSY-002', 'Maria', 'Luisa', 'Fernandez', 'student2@cvsu.edu.ph',
 '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6', '00000000-0000-0000-0000-000000000003', 'ACTIVE', 'BS Psychology', NOW() - INTERVAL '85 days'),

('10000000-0000-0000-0000-000000000015', '2024-PSY-005', 'Diego', 'Luis', 'Bautista', 'student5@cvsu.edu.ph',
 '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6', '00000000-0000-0000-0000-000000000003', 'PENDING', 'BS Psychology', NOW() - INTERVAL '5 days')
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 4. SUBJECTS (Now with weight and passing_rate)
-- ────────────────────────────────────────────────────────────
INSERT INTO subjects (id, name, description, color, weight, passing_rate, status, created_by, created_at, updated_at) VALUES
('30000000-0000-0000-0000-000000000001', 'General Psychology', 'Foundational concepts, theories, and applications of psychology.', '#6366f1', 20, 75, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '160 days', NOW() - INTERVAL '160 days'),
('30000000-0000-0000-0000-000000000002', 'Developmental Psychology', 'Human development across the lifespan from infancy through late adulthood.', '#8b5cf6', 20, 75, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '155 days', NOW() - INTERVAL '155 days'),
('30000000-0000-0000-0000-000000000003', 'Abnormal Psychology', 'Classification, etiology, assessment, and treatment of psychological disorders.', '#ec4899', 20, 75, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '150 days', NOW() - INTERVAL '150 days')
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 5. MODULES (Now handles TEXT and PDF formats)
-- ────────────────────────────────────────────────────────────
INSERT INTO modules (id, subject_id, parent_id, title, description, content, format, file_url, file_name, sort_order, status, created_by, created_at) VALUES
('40000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', NULL,
 'History and Schools of Thought', 'Major schools of psychology.', 
 'Psychology evolved from philosophy and physiology. Wilhelm Wundt founded the first psychology lab in 1879.', 
 'TEXT', NULL, NULL, 1, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '158 days'),

('40000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000001', NULL,
 'Research Methods in Psychology', 'Scientific method and stats.', 
 'The scientific method involves: identifying a problem, forming a hypothesis, designing a study, collecting data, analyzing results, drawing conclusions, and communicating findings.', 
 'TEXT', NULL, NULL, 2, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '157 days'),

('40000000-0000-0000-0000-000000000003', '30000000-0000-0000-0000-000000000001', NULL,
 'Biological Bases of Behavior', 'Nervous system and brain.', NULL, 
 'TEXT', NULL, NULL, 3, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '156 days'),

-- Submodules (This one is seeded as a PDF for testing!)
('40000000-0000-0000-0000-000000000004', '30000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000003',
 'Neurons and Neural Communication', 'A comprehensive visual guide to neural structures.', 
 NULL, 
 'PDF', 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf', 'neurons_guide.pdf', 1, 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '155 days')
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 6. ASSESSMENTS (Excluding JSON Questions)
-- ────────────────────────────────────────────────────────────
INSERT INTO assessments (
    id, title, type, subject_id, module_id,
    items, status, author_id, created_at, updated_at
) VALUES
('60000000-0000-0000-0000-000000000001', 'General Psychology — Pre-Assessment', 'PRE_ASSESSMENT', '30000000-0000-0000-0000-000000000001', NULL, 5, 'APPROVED', '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '138 days', NOW() - INTERVAL '138 days'),
('60000000-0000-0000-0000-000000000002', 'Neurons and Neural Communication — Quiz', 'QUIZ', '30000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000004', 5, 'APPROVED', '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '128 days', NOW() - INTERVAL '128 days')
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 7. QUESTIONS (Relational mappings for Assessments)
-- Note: 'correct_answer' is the 0-based index of the array
-- ────────────────────────────────────────────────────────────
INSERT INTO questions (id, assessment_id, author_id, text, options, correct_answer) VALUES
-- Assessment 1: Gen Psych Pre-Assessment
(gen_random_uuid(), '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002', 
 'Who founded the first experimental psychology laboratory in 1879?', 
 '["Sigmund Freud", "William James", "Wilhelm Wundt", "John Watson"]'::jsonb, 2),
 
(gen_random_uuid(), '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002', 
 'Which approach emphasizes unconscious processes and early childhood?', 
 '["Behaviorism", "Psychoanalysis", "Humanism", "Structuralism"]'::jsonb, 1),
 
(gen_random_uuid(), '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002', 
 'The biopsychosocial model considers which three dimensions?', 
 '["Biological, psychological, social", "Physical, mental, spiritual", "Genetic, behavioral, cultural", "Neural, cognitive, emotional"]'::jsonb, 0),

(gen_random_uuid(), '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002', 
 'A researcher manipulates the IV and measures the DV. What type of study?', 
 '["Correlational", "Naturalistic observation", "Experiment", "Case study"]'::jsonb, 2),

(gen_random_uuid(), '60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000002', 
 'Which neurotransmitter is primarily associated with reward and motivation?', 
 '["Serotonin", "GABA", "Dopamine", "Acetylcholine"]'::jsonb, 2),

-- Assessment 2: Neurons Quiz
(gen_random_uuid(), '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 
 'What is the resting membrane potential of a typical neuron?', 
 '["-70 mV", "+70 mV", "-50 mV", "0 mV"]'::jsonb, 0),

(gen_random_uuid(), '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 
 'Which part of the neuron receives incoming signals?', 
 '["Axon", "Axon terminals", "Dendrites", "Myelin sheath"]'::jsonb, 2),

(gen_random_uuid(), '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 
 'The myelin sheath functions to:', 
 '["Generate neurotransmitters", "Increase signal transmission speed", "Store memories", "Control hormones"]'::jsonb, 1),
 
(gen_random_uuid(), '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 
 'Which neurotransmitter is the primary inhibitory neurotransmitter?', 
 '["Glutamate", "Dopamine", "GABA", "Norepinephrine"]'::jsonb, 2),

(gen_random_uuid(), '60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 
 'The gap between two neurons is called:', 
 '["Axon hillock", "Synapse", "Node of Ranvier", "Soma"]'::jsonb, 1);

-- ────────────────────────────────────────────────────────────
-- 8. ASSESSMENT RESULTS 
-- ────────────────────────────────────────────────────────────
INSERT INTO assessment_results (id, assessment_id, user_id, score, total_items, date_taken) VALUES
('70000000-0000-0000-0001-000000000001','60000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000011', 3, 5, NOW() - INTERVAL '58 days'),
('70000000-0000-0000-0001-000000000002','60000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000011', 5, 5, NOW() - INTERVAL '50 days'),
('70000000-0000-0000-0002-000000000001','60000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000012', 4, 5, NOW() - INTERVAL '55 days')
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 9. REQUEST CHANGES (Polymorphic Revision Workflow)
-- ────────────────────────────────────────────────────────────
INSERT INTO request_changes (id, target_id, created_by, type, content, revisions_list) VALUES
('b0000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000002', 'MODULE',
 '{"title": "Neurons and Neural Communication (Updated)", "content": "Updated content: added section on demyelinating diseases such as Multiple Sclerosis."}'::jsonb,
 '[
    {
      "notes": "The content on myelination is brief. Please add a section on demyelinating diseases.", 
      "status": "PENDING", 
      "author_id": "10000000-0000-0000-0000-000000000001"
    }
  ]'::jsonb
) ON CONFLICT (id) DO NOTHING;

INSERT INTO activity_logs (id, user_id, action, target, ip_address, created_at) VALUES
(gen_random_uuid(), '10000000-0000-0000-0000-000000000001', 'User logged in', 'admin@cvsu.edu.ph', '127.0.0.1', NOW() - INTERVAL '2 hours'),
(gen_random_uuid(), '10000000-0000-0000-0000-000000000002', 'Created new assessment', 'General Psychology — Pre-Assessment', '127.0.0.1', NOW() - INTERVAL '5 hours'),
(gen_random_uuid(), '10000000-0000-0000-0000-000000000001', 'Approved subject change', 'General Psychology', '127.0.0.1', NOW() - INTERVAL '1 day')
ON CONFLICT DO NOTHING;

COMMIT;