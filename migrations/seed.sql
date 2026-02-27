-- ============================================================
-- seed.sql  —  psych_db initial dataset
-- Run AFTER schema.sql
-- Passwords are bcrypt hashes of the plain-text shown in comments.
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
    1, FALSE, NULL,
    TRUE, FALSE,
    75, 'Philippine Psychology Review Institute', '2024-2025', NOW()
) ON CONFLICT (id) DO NOTHING;


-- ────────────────────────────────────────────────────────────
-- 2. ROLES  (system roles, cannot be deleted)
-- ────────────────────────────────────────────────────────────
INSERT INTO roles (id, name, permissions, is_system, created_at) VALUES
    ('00000000-0000-0000-0000-000000000001', 'ADMIN',
        '["manage_users","manage_content","manage_assessments","manage_subjects",
          "manage_settings","view_analytics","approve_content","manage_whitelist",
          "view_logs","manage_roles"]',
        TRUE, NOW()),
    ('00000000-0000-0000-0000-000000000002', 'FACULTY',
        '["create_content","submit_content","create_assessments","submit_assessments",
          "view_analytics","manage_student_whitelist","view_subjects"]',
        TRUE, NOW()),
    ('00000000-0000-0000-0000-000000000003', 'STUDENT',
        '["view_content","take_assessments","view_progress","view_subjects"]',
        TRUE, NOW())
ON CONFLICT (id) DO NOTHING;


-- ────────────────────────────────────────────────────────────
-- 3. USERS
-- Passwords (bcrypt $2b$12$ rounds):
--   admin@ppri.edu       → Admin@1234
--   faculty1@ppri.edu    → Faculty@1234
--   faculty2@ppri.edu    → Faculty@1234
--   student1–5@ppri.edu  → Student@1234
-- ────────────────────────────────────────────────────────────
INSERT INTO users (
    id, institutional_id, first_name, middle_name, last_name,
    email, password, role_id, status, department, date_created
) VALUES
-- ── Admin ────────────────────────────────────────────────────
('10000000-0000-0000-0000-000000000001',
 'ADMIN-001', 'Ana', 'Cruz', 'Reyes',
 'admin@ppri.edu',
 '$2b$12$KIXbhELtNrGF7JK7CzIxiONH5V7M3G0GzGPHMK5JxGmE0s0P2yOZC',
 '00000000-0000-0000-0000-000000000001', 'ACTIVE', 'Administration', NOW() - INTERVAL '180 days'),

-- ── Faculty ──────────────────────────────────────────────────
('10000000-0000-0000-0000-000000000002',
 'FAC-2024-001', 'Marco', 'Antonio', 'Santos',
 'faculty1@ppri.edu',
 '$2b$12$X8RhYvBn7MtK3O4P5qAh8eP2Z3KMQd9hW1aJlH4yNxVRmUxS1sOaC',
 '00000000-0000-0000-0000-000000000002', 'ACTIVE', 'Developmental Psychology', NOW() - INTERVAL '150 days'),

('10000000-0000-0000-0000-000000000003',
 'FAC-2024-002', 'Elena', 'Grace', 'Villanueva',
 'faculty2@ppri.edu',
 '$2b$12$X8RhYvBn7MtK3O4P5qAh8eP2Z3KMQd9hW1aJlH4yNxVRmUxS1sOaC',
 '00000000-0000-0000-0000-000000000002', 'ACTIVE', 'Clinical Psychology', NOW() - INTERVAL '120 days'),

-- ── Students ─────────────────────────────────────────────────
('10000000-0000-0000-0000-000000000011',
 '2024-PSY-001', 'Jose', 'Miguel', 'Garcia',
 'student1@ppri.edu',
 '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
 '00000000-0000-0000-0000-000000000003', 'ACTIVE', 'BS Psychology', NOW() - INTERVAL '90 days'),

('10000000-0000-0000-0000-000000000012',
 '2024-PSY-002', 'Maria', 'Luisa', 'Fernandez',
 'student2@ppri.edu',
 '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
 '00000000-0000-0000-0000-000000000003', 'ACTIVE', 'BS Psychology', NOW() - INTERVAL '85 days'),

('10000000-0000-0000-0000-000000000013',
 '2024-PSY-003', 'Ricardo', 'Paulo', 'Mendoza',
 'student3@ppri.edu',
 '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
 '00000000-0000-0000-0000-000000000003', 'ACTIVE', 'BS Psychology', NOW() - INTERVAL '80 days'),

('10000000-0000-0000-0000-000000000014',
 '2024-PSY-004', 'Clara', 'Rose', 'Torres',
 'student4@ppri.edu',
 '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
 '00000000-0000-0000-0000-000000000003', 'ACTIVE', 'BS Psychology', NOW() - INTERVAL '75 days'),

('10000000-0000-0000-0000-000000000015',
 '2024-PSY-005', 'Diego', 'Luis', 'Bautista',
 'student5@ppri.edu',
 '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
 '00000000-0000-0000-0000-000000000003', 'PENDING', 'BS Psychology', NOW() - INTERVAL '5 days')
ON CONFLICT (id) DO NOTHING;


-- ────────────────────────────────────────────────────────────
-- 4. WHITELIST
-- ────────────────────────────────────────────────────────────
INSERT INTO whitelist (
    id, first_name, middle_name, last_name,
    institutional_id, email, role, status, date_added
) VALUES
-- Faculty whitelist entries
('20000000-0000-0000-0000-000000000001',
 'Marco',  'Antonio', 'Santos',    'FAC-2024-001', 'faculty1@ppri.edu', 'FACULTY', 'REGISTERED', NOW() - INTERVAL '160 days'),
('20000000-0000-0000-0000-000000000002',
 'Elena',  'Grace',   'Villanueva','FAC-2024-002', 'faculty2@ppri.edu', 'FACULTY', 'REGISTERED', NOW() - INTERVAL '130 days'),
-- Student whitelist entries
('20000000-0000-0000-0000-000000000011',
 'Jose',   'Miguel',  'Garcia',    '2024-PSY-001', 'student1@ppri.edu', 'STUDENT', 'REGISTERED', NOW() - INTERVAL '100 days'),
('20000000-0000-0000-0000-000000000012',
 'Maria',  'Luisa',   'Fernandez', '2024-PSY-002', 'student2@ppri.edu', 'STUDENT', 'REGISTERED', NOW() - INTERVAL '95 days'),
('20000000-0000-0000-0000-000000000013',
 'Ricardo','Paulo',   'Mendoza',   '2024-PSY-003', 'student3@ppri.edu', 'STUDENT', 'REGISTERED', NOW() - INTERVAL '90 days'),
('20000000-0000-0000-0000-000000000014',
 'Clara',  'Rose',    'Torres',    '2024-PSY-004', 'student4@ppri.edu', 'STUDENT', 'REGISTERED', NOW() - INTERVAL '85 days'),
('20000000-0000-0000-0000-000000000015',
 'Diego',  'Luis',    'Bautista',  '2024-PSY-005', 'student5@ppri.edu', 'STUDENT', 'REGISTERED', NOW() - INTERVAL '10 days'),
-- Pending (not yet registered) students
('20000000-0000-0000-0000-000000000016',
 'Sofia',  NULL,      'Aquino',    '2024-PSY-006', 'student6@ppri.edu', 'STUDENT', 'PENDING',    NOW() - INTERVAL '3 days'),
('20000000-0000-0000-0000-000000000017',
 'Miguel', NULL,      'Cruz',      '2024-PSY-007', 'student7@ppri.edu', 'STUDENT', 'PENDING',    NOW() - INTERVAL '2 days')
ON CONFLICT (id) DO NOTHING;


-- ────────────────────────────────────────────────────────────
-- 5. SUBJECTS
-- ────────────────────────────────────────────────────────────
INSERT INTO subjects (id, name, description, color, status, created_by, created_at, updated_at) VALUES
('30000000-0000-0000-0000-000000000001',
 'General Psychology',
 'Foundational concepts, theories, and applications of psychology covering behavior, cognition, and mental processes.',
 '#6366f1', 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '160 days', NOW() - INTERVAL '160 days'),

('30000000-0000-0000-0000-000000000002',
 'Developmental Psychology',
 'Human development across the lifespan from infancy through late adulthood, including physical, cognitive, and social development.',
 '#8b5cf6', 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '155 days', NOW() - INTERVAL '155 days'),

('30000000-0000-0000-0000-000000000003',
 'Abnormal Psychology',
 'Classification, etiology, assessment, and treatment of psychological disorders and abnormal behavior patterns.',
 '#ec4899', 'APPROVED', '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '150 days', NOW() - INTERVAL '150 days'),

('30000000-0000-0000-0000-000000000004',
 'Social Psychology',
 'How individuals think, feel, and behave in social contexts; group dynamics, attitudes, persuasion, and social influence.',
 '#22c55e', 'APPROVED', '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '140 days', NOW() - INTERVAL '140 days'),

('30000000-0000-0000-0000-000000000005',
 'Psychological Assessment',
 'Principles and practices of psychological testing, measurement, and evaluation including intelligence and personality tests.',
 '#f97316', 'APPROVED', '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '130 days', NOW() - INTERVAL '130 days'),

('30000000-0000-0000-0000-000000000006',
 'Industrial-Organizational Psychology',
 'Application of psychological principles and research methods to workplace settings, covering personnel, motivation, and organizational behavior.',
 '#14b8a6', 'PENDING', '10000000-0000-0000-0000-000000000003', NOW() - INTERVAL '5 days', NOW() - INTERVAL '5 days')
ON CONFLICT (id) DO NOTHING;


-- ────────────────────────────────────────────────────────────
-- 6. TOPICS
-- ────────────────────────────────────────────────────────────
INSERT INTO topics (id, subject_id, parent_id, title, description, sort_order, status, created_by, created_at) VALUES

-- General Psychology
('40000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', NULL,
 'History and Schools of Thought',
 'Major schools of psychology from structuralism to contemporary cognitive neuroscience.', 1, 'APPROVED',
 '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '158 days'),
('40000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000001', NULL,
 'Research Methods in Psychology',
 'Scientific method, experimental design, statistics, and ethical considerations in psychological research.', 2, 'APPROVED',
 '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '157 days'),
('40000000-0000-0000-0000-000000000003', '30000000-0000-0000-0000-000000000001', NULL,
 'Biological Bases of Behavior',
 'Nervous system, brain structure, neurotransmitters, genetics, and their influence on behavior.', 3, 'APPROVED',
 '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '156 days'),
-- Subtopics under Biological Bases
('40000000-0000-0000-0000-000000000004', '30000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000003',
 'Neurons and Neural Communication', NULL, 1, 'APPROVED',
 '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '155 days'),
('40000000-0000-0000-0000-000000000005', '30000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000003',
 'Brain Structures and Functions', NULL, 2, 'APPROVED',
 '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '154 days'),
('40000000-0000-0000-0000-000000000006', '30000000-0000-0000-0000-000000000001', NULL,
 'Sensation and Perception', NULL, 4, 'APPROVED',
 '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '150 days'),
('40000000-0000-0000-0000-000000000007', '30000000-0000-0000-0000-000000000001', NULL,
 'States of Consciousness', NULL, 5, 'APPROVED',
 '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '148 days'),
('40000000-0000-0000-0000-000000000008', '30000000-0000-0000-0000-000000000001', NULL,
 'Learning and Conditioning', NULL, 6, 'APPROVED',
 '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '146 days'),
('40000000-0000-0000-0000-000000000009', '30000000-0000-0000-0000-000000000001', NULL,
 'Memory',
 'Encoding, storage, retrieval, and forgetting.', 7, 'APPROVED',
 '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '144 days'),
('40000000-0000-0000-0000-000000000010', '30000000-0000-0000-0000-000000000001', NULL,
 'Motivation and Emotion', NULL, 8, 'APPROVED',
 '10000000-0000-0000-0000-000000000001', NOW() - INTERVAL '142 days'),

-- Developmental Psychology
('40000000-0000-0000-0000-000000000011', '30000000-0000-0000-0000-000000000002', NULL,
 'Prenatal Development and Birth', NULL, 1, 'APPROVED',
 '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '150 days'),
('40000000-0000-0000-0000-000000000012', '30000000-0000-0000-0000-000000000002', NULL,
 'Infancy and Toddlerhood', NULL, 2, 'APPROVED',
 '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '148 days'),
('40000000-0000-0000-0000-000000000013', '30000000-0000-0000-0000-000000000002', NULL,
 'Early and Middle Childhood', NULL, 3, 'APPROVED',
 '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '146 days'),
('40000000-0000-0000-0000-000000000014', '30000000-0000-0000-0000-000000000002', NULL,
 'Adolescence', NULL, 4, 'APPROVED',
 '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '144 days'),
('40000000-0000-0000-0000-000000000015', '30000000-0000-0000-0000-000000000002', NULL,
 'Adulthood and Aging', NULL, 5, 'APPROVED',
 '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '142 days'),

-- Abnormal Psychology
('40000000-0000-0000-0000-000000000021', '30000000-0000-0000-0000-000000000003', NULL,
 'Models of Abnormality', NULL, 1, 'APPROVED',
 '10000000-0000-0000-0000-000000000003', NOW() - INTERVAL '145 days'),
('40000000-0000-0000-0000-000000000022', '30000000-0000-0000-0000-000000000003', NULL,
 'Anxiety Disorders', NULL, 2, 'APPROVED',
 '10000000-0000-0000-0000-000000000003', NOW() - INTERVAL '143 days'),
('40000000-0000-0000-0000-000000000023', '30000000-0000-0000-0000-000000000003', NULL,
 'Mood Disorders', NULL, 3, 'APPROVED',
 '10000000-0000-0000-0000-000000000003', NOW() - INTERVAL '141 days'),
('40000000-0000-0000-0000-000000000024', '30000000-0000-0000-0000-000000000003', NULL,
 'Schizophrenia Spectrum Disorders', NULL, 4, 'APPROVED',
 '10000000-0000-0000-0000-000000000003', NOW() - INTERVAL '139 days'),

-- Social Psychology
('40000000-0000-0000-0000-000000000031', '30000000-0000-0000-0000-000000000004', NULL,
 'Social Cognition and Perception', NULL, 1, 'APPROVED',
 '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '135 days'),
('40000000-0000-0000-0000-000000000032', '30000000-0000-0000-0000-000000000004', NULL,
 'Attitudes and Attitude Change', NULL, 2, 'APPROVED',
 '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '133 days'),
('40000000-0000-0000-0000-000000000033', '30000000-0000-0000-0000-000000000004', NULL,
 'Social Influence', NULL, 3, 'APPROVED',
 '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '131 days'),

-- Psychological Assessment
('40000000-0000-0000-0000-000000000041', '30000000-0000-0000-0000-000000000005', NULL,
 'Principles of Psychological Testing', NULL, 1, 'APPROVED',
 '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '125 days'),
('40000000-0000-0000-0000-000000000042', '30000000-0000-0000-0000-000000000005', NULL,
 'Intelligence and Cognitive Assessment', NULL, 2, 'APPROVED',
 '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '123 days'),
('40000000-0000-0000-0000-000000000043', '30000000-0000-0000-0000-000000000005', NULL,
 'Personality Assessment', NULL, 3, 'APPROVED',
 '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '121 days')
ON CONFLICT (id) DO NOTHING;


-- ────────────────────────────────────────────────────────────
-- 7. CONTENT MODULES
-- ────────────────────────────────────────────────────────────
INSERT INTO content_modules (
    id, title, subject_id, topic_id, content, format, status,
    revision_notes, submission_count, author_id, author_name,
    last_updated, date_created
) VALUES
-- General Psychology modules
('50000000-0000-0000-0000-000000000001',
 'Introduction to Psychology: A Brief History',
 '30000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000001',
 'Psychology evolved from philosophy and physiology. Wilhelm Wundt founded the first psychology lab in 1879 in Leipzig, Germany, marking the birth of psychology as an empirical science. Major schools include Structuralism (Wundt, Titchener), Functionalism (James), Behaviorism (Watson, Skinner), Gestalt (Wertheimer), Psychoanalysis (Freud), Humanistic (Maslow, Rogers), Cognitive, and the current Biopsychosocial approach.',
 'TEXT', 'APPROVED', '[]', 1, '10000000-0000-0000-0000-000000000002',
 'Marco Santos', NOW() - INTERVAL '140 days', NOW() - INTERVAL '145 days'),

('50000000-0000-0000-0000-000000000002',
 'Research Methods: Experimental Design Basics',
 '30000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000002',
 'The scientific method involves: (1) identifying a problem, (2) forming a hypothesis, (3) designing a study, (4) collecting data, (5) analyzing results, (6) drawing conclusions, and (7) communicating findings. Key concepts: independent variable (IV), dependent variable (DV), operational definitions, random assignment, control groups, confounds, and replication.',
 'TEXT', 'APPROVED', '[]', 1, '10000000-0000-0000-0000-000000000002',
 'Marco Santos', NOW() - INTERVAL '135 days', NOW() - INTERVAL '140 days'),

('50000000-0000-0000-0000-000000000003',
 'The Neuron: Structure and Function',
 '30000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000004',
 'Neurons are specialized cells that transmit information. Key parts: dendrites (receive signals), cell body/soma, axon (transmits signals), axon terminals, myelin sheath (speeds transmission). Types: sensory, motor, interneurons. Neural communication involves: resting potential (-70mV), action potential, refractory period, and synaptic transmission via neurotransmitters (e.g., dopamine, serotonin, acetylcholine, GABA, glutamate).',
 'TEXT', 'APPROVED', '[]', 2, '10000000-0000-0000-0000-000000000002',
 'Marco Santos', NOW() - INTERVAL '130 days', NOW() - INTERVAL '135 days'),

('50000000-0000-0000-0000-000000000004',
 'Brain Anatomy: Lobes and Their Functions',
 '30000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000005',
 'The cerebral cortex is divided into 4 lobes: (1) Frontal — reasoning, planning, motor control, Broca''s area; (2) Parietal — sensory processing, spatial awareness, somatosensory cortex; (3) Occipital — visual processing; (4) Temporal — auditory processing, language comprehension, Wernicke''s area. Key subcortical structures: hippocampus (memory), amygdala (emotion/fear), thalamus (relay station), hypothalamus (homeostasis), cerebellum (coordination), brainstem (basic life functions).',
 'TEXT', 'APPROVED', '[]', 1, '10000000-0000-0000-0000-000000000003',
 'Elena Villanueva', NOW() - INTERVAL '125 days', NOW() - INTERVAL '130 days'),

-- Developmental Psychology modules
('50000000-0000-0000-0000-000000000005',
 'Theories of Development: Piaget, Vygotsky, Erikson',
 '30000000-0000-0000-0000-000000000002', '40000000-0000-0000-0000-000000000013',
 'Piaget''s Cognitive Stages: Sensorimotor (0-2), Preoperational (2-7), Concrete Operational (7-11), Formal Operational (12+). Key concepts: schemas, assimilation, accommodation, equilibration, object permanence, conservation. Vygotsky: Zone of Proximal Development (ZPD), scaffolding, social learning. Erikson''s 8 Psychosocial Stages: Trust vs. Mistrust → Integrity vs. Despair.',
 'TEXT', 'APPROVED', '[]', 1, '10000000-0000-0000-0000-000000000002',
 'Marco Santos', NOW() - INTERVAL '120 days', NOW() - INTERVAL '125 days'),

('50000000-0000-0000-0000-000000000006',
 'Adolescent Development: Identity and Peer Influence',
 '30000000-0000-0000-0000-000000000002', '40000000-0000-0000-0000-000000000014',
 'Adolescence (12–18 years) is characterized by puberty, formal operational thinking, and identity formation. Erikson''s stage 5: Identity vs. Role Confusion — Marcia''s four identity statuses: diffusion, foreclosure, moratorium, and achievement. Social influences: peer relationships, social media, family communication styles. Adolescent brain: prefrontal cortex still developing (impulse control, risk assessment).',
 'TEXT', 'APPROVED', '[]', 1, '10000000-0000-0000-0000-000000000002',
 'Marco Santos', NOW() - INTERVAL '115 days', NOW() - INTERVAL '120 days'),

-- Abnormal Psychology modules
('50000000-0000-0000-0000-000000000007',
 'The DSM-5 and Classification of Mental Disorders',
 '30000000-0000-0000-0000-000000000003', '40000000-0000-0000-0000-000000000021',
 'The DSM-5 (Diagnostic and Statistical Manual of Mental Disorders, 5th Edition, 2013) uses a categorical classification system. Key changes from DSM-IV: removal of multiaxial system, addition of specifiers and dimensional assessments. Major categories: Neurodevelopmental, Schizophrenia Spectrum, Bipolar, Depressive, Anxiety, OCD-related, Trauma-related, Dissociative, Somatic, Feeding/Eating, Elimination, Sleep-Wake, Sexual, Gender Dysphoria, Disruptive, Substance-related, Neurocognitive, Personality, Paraphilic disorders.',
 'TEXT', 'APPROVED', '[]', 2, '10000000-0000-0000-0000-000000000003',
 'Elena Villanueva', NOW() - INTERVAL '110 days', NOW() - INTERVAL '115 days'),

('50000000-0000-0000-0000-000000000008',
 'Anxiety Disorders: Overview and Treatment',
 '30000000-0000-0000-0000-000000000003', '40000000-0000-0000-0000-000000000022',
 'Anxiety disorders are the most prevalent mental disorders. Types: Generalized Anxiety Disorder (GAD), Panic Disorder, Specific Phobias, Social Anxiety Disorder (SAD), Agoraphobia, Separation Anxiety. Core feature: excessive fear/anxiety disproportionate to the actual threat. Biological: amygdala hyperactivation, HPA axis dysregulation. Psychological: cognitive distortions (catastrophizing, overestimation of threat). Treatment: CBT (first-line), exposure therapy, SSRIs/SNRIs, benzodiazepines (short-term).',
 'TEXT', 'APPROVED', '[]', 1, '10000000-0000-0000-0000-000000000003',
 'Elena Villanueva', NOW() - INTERVAL '100 days', NOW() - INTERVAL '105 days'),

-- Social Psychology modules
('50000000-0000-0000-0000-000000000009',
 'Attribution Theory and Social Cognition',
 '30000000-0000-0000-0000-000000000004', '40000000-0000-0000-0000-000000000031',
 'Attribution theory (Heider, Kelley, Weiner) explains how people interpret behavior. Dispositional vs. situational attributions. Fundamental Attribution Error (FAE): overestimating dispositional, underestimating situational factors. Actor-Observer Bias: we attribute others'' behavior to dispositional factors but our own to situational. Self-serving bias: success → internal, failure → external. Kelley''s covariation model: consistency, distinctiveness, consensus.',
 'TEXT', 'APPROVED', '[]', 1, '10000000-0000-0000-0000-000000000002',
 'Marco Santos', NOW() - INTERVAL '95 days', NOW() - INTERVAL '100 days'),

-- Pending/draft module
('50000000-0000-0000-0000-000000000010',
 'Psychological Assessment Tools: MMPI and Rorschach',
 '30000000-0000-0000-0000-000000000005', '40000000-0000-0000-0000-000000000043',
 'MMPI-2 (Minnesota Multiphasic Personality Inventory-2): 567 true/false items, 10 clinical scales (Hypochondriasis, Depression, Hysteria, Psychopathic Deviate, Masculinity-Femininity, Paranoia, Psychasthenia, Schizophrenia, Mania, Social Introversion) plus validity scales. Rorschach Inkblot Test: projective technique, Exner Comprehensive System, evaluates perception, thought organization, and personality dynamics.',
 'TEXT', 'PENDING', '[]', 1, '10000000-0000-0000-0000-000000000003',
 'Elena Villanueva', NOW() - INTERVAL '5 days', NOW() - INTERVAL '7 days')
ON CONFLICT (id) DO NOTHING;


-- ────────────────────────────────────────────────────────────
-- 8. ASSESSMENTS
-- questions column: JSON array of {id, text, options[], answer}
-- answer = the exact text of the correct option (matched case-insensitively by backend)
-- ────────────────────────────────────────────────────────────
INSERT INTO assessments (
    id, title, type, subject_id, topic_id,
    questions, items, status, author_id, created_at, updated_at
) VALUES

-- ── General Psychology — Pre-Assessment ──────────────────────
('60000000-0000-0000-0000-000000000001',
 'General Psychology — Pre-Assessment',
 'PRE_ASSESSMENT', '30000000-0000-0000-0000-000000000001', NULL,
 '[
   {"id":"q001","text":"Who is credited with founding the first experimental psychology laboratory in 1879?",
    "options":["Sigmund Freud","William James","Wilhelm Wundt","John Watson"],
    "answer":"Wilhelm Wundt"},
   {"id":"q002","text":"Which approach emphasizes the role of unconscious processes and early childhood experiences?",
    "options":["Behaviorism","Psychoanalysis","Humanism","Structuralism"],
    "answer":"Psychoanalysis"},
   {"id":"q003","text":"The biopsychosocial model considers which three dimensions?",
    "options":["Biological, psychological, social","Physical, mental, spiritual","Genetic, behavioral, cultural","Neural, cognitive, emotional"],
    "answer":"Biological, psychological, social"},
   {"id":"q004","text":"A researcher manipulates the IV and measures the DV. What type of study is this?",
    "options":["Correlational","Naturalistic observation","Experiment","Case study"],
    "answer":"Experiment"},
   {"id":"q005","text":"Which neurotransmitter is primarily associated with reward and motivation?",
    "options":["Serotonin","GABA","Dopamine","Acetylcholine"],
    "answer":"Dopamine"}
 ]',
 5, 'APPROVED', '10000000-0000-0000-0000-000000000002',
 NOW() - INTERVAL '138 days', NOW() - INTERVAL '138 days'),

-- ── General Psychology — Quiz (Neurons) ──────────────────────
('60000000-0000-0000-0000-000000000002',
 'Neurons and Neural Communication — Quiz',
 'QUIZ', '30000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000004',
 '[
   {"id":"q010","text":"What is the resting membrane potential of a typical neuron?",
    "options":["-70 mV","+70 mV","-50 mV","0 mV"],
    "answer":"-70 mV"},
   {"id":"q011","text":"Which part of the neuron receives incoming signals from other neurons?",
    "options":["Axon","Axon terminals","Dendrites","Myelin sheath"],
    "answer":"Dendrites"},
   {"id":"q012","text":"The myelin sheath functions to:",
    "options":["Generate neurotransmitters","Increase signal transmission speed","Store memories","Control hormones"],
    "answer":"Increase signal transmission speed"},
   {"id":"q013","text":"Which neurotransmitter is the brain''s primary inhibitory neurotransmitter?",
    "options":["Glutamate","Dopamine","GABA","Norepinephrine"],
    "answer":"GABA"},
   {"id":"q014","text":"The gap between two neurons is called:",
    "options":["Axon hillock","Synapse","Node of Ranvier","Soma"],
    "answer":"Synapse"},
   {"id":"q015","text":"Which type of neuron carries signals FROM the CNS to muscles?",
    "options":["Sensory neuron","Interneuron","Motor neuron","Mirror neuron"],
    "answer":"Motor neuron"}
 ]',
 6, 'APPROVED', '10000000-0000-0000-0000-000000000002',
 NOW() - INTERVAL '128 days', NOW() - INTERVAL '128 days'),

-- ── General Psychology — Post-Assessment ─────────────────────
('60000000-0000-0000-0000-000000000003',
 'General Psychology — Post-Assessment',
 'POST_ASSESSMENT', '30000000-0000-0000-0000-000000000001', NULL,
 '[
   {"id":"q020","text":"Which brain lobe is primarily responsible for language production (Broca''s area)?",
    "options":["Occipital","Parietal","Temporal","Frontal"],
    "answer":"Frontal"},
   {"id":"q021","text":"Classical conditioning was developed by:",
    "options":["B.F. Skinner","John Watson","Ivan Pavlov","Albert Bandura"],
    "answer":"Ivan Pavlov"},
   {"id":"q022","text":"The hippocampus is critical for:",
    "options":["Visual processing","Emotional regulation","Memory formation","Motor coordination"],
    "answer":"Memory formation"},
   {"id":"q023","text":"Negative reinforcement involves:",
    "options":["Adding an aversive stimulus","Removing an aversive stimulus","Punishing a behavior","Ignoring a behavior"],
    "answer":"Removing an aversive stimulus"},
   {"id":"q024","text":"According to Maslow''s hierarchy, which need must be met first?",
    "options":["Safety","Esteem","Physiological","Love and belonging"],
    "answer":"Physiological"},
   {"id":"q025","text":"A self-fulfilling prophecy is an example of which psychological concept?",
    "options":["Cognitive dissonance","Confirmation bias","Behavioral confirmation","Fundamental attribution error"],
    "answer":"Behavioral confirmation"},
   {"id":"q026","text":"Which memory system holds information for 15–30 seconds?",
    "options":["Long-term memory","Sensory memory","Short-term / working memory","Procedural memory"],
    "answer":"Short-term / working memory"},
   {"id":"q027","text":"The James-Lange theory of emotion proposes that:",
    "options":["Emotions cause physiological responses","Physiological responses cause emotions","Emotions and physiology occur simultaneously","The thalamus generates emotions directly"],
    "answer":"Physiological responses cause emotions"},
   {"id":"q028","text":"Circadian rhythms are regulated primarily by the:",
    "options":["Cerebellum","Amygdala","Suprachiasmatic nucleus","Hippocampus"],
    "answer":"Suprachiasmatic nucleus"},
   {"id":"q029","text":"Which research method allows researchers to establish cause-and-effect relationships?",
    "options":["Survey","Naturalistic observation","Experiment","Case study"],
    "answer":"Experiment"}
 ]',
 10, 'APPROVED', '10000000-0000-0000-0000-000000000002',
 NOW() - INTERVAL '120 days', NOW() - INTERVAL '120 days'),

-- ── Developmental Psychology — Pre-Assessment ────────────────
('60000000-0000-0000-0000-000000000004',
 'Developmental Psychology — Pre-Assessment',
 'PRE_ASSESSMENT', '30000000-0000-0000-0000-000000000002', NULL,
 '[
   {"id":"q040","text":"Piaget''s first stage of cognitive development (0–2 years) is called:",
    "options":["Preoperational","Sensorimotor","Concrete Operational","Formal Operational"],
    "answer":"Sensorimotor"},
   {"id":"q041","text":"Object permanence is achieved during which Piagetian stage?",
    "options":["Sensorimotor","Preoperational","Concrete Operational","Formal Operational"],
    "answer":"Sensorimotor"},
   {"id":"q042","text":"Vygotsky''s zone of proximal development refers to:",
    "options":["Tasks a child cannot yet do","Tasks a child can do alone","Tasks between what a child can do alone and with guidance","A child''s highest potential"],
    "answer":"Tasks between what a child can do alone and with guidance"},
   {"id":"q043","text":"Erikson''s first psychosocial stage is:",
    "options":["Autonomy vs. Shame","Trust vs. Mistrust","Industry vs. Inferiority","Initiative vs. Guilt"],
    "answer":"Trust vs. Mistrust"},
   {"id":"q044","text":"Which theorist proposed the concept of scaffolding?",
    "options":["Piaget","Erikson","Freud","Vygotsky"],
    "answer":"Vygotsky"}
 ]',
 5, 'APPROVED', '10000000-0000-0000-0000-000000000002',
 NOW() - INTERVAL '118 days', NOW() - INTERVAL '118 days'),

-- ── Abnormal Psychology — Pre-Assessment ─────────────────────
('60000000-0000-0000-0000-000000000005',
 'Abnormal Psychology — Pre-Assessment',
 'PRE_ASSESSMENT', '30000000-0000-0000-0000-000000000003', NULL,
 '[
   {"id":"q050","text":"The DSM-5 was published in which year?",
    "options":["2000","2007","2013","2018"],
    "answer":"2013"},
   {"id":"q051","text":"Which anxiety disorder is characterized by recurrent, unexpected panic attacks?",
    "options":["Generalized Anxiety Disorder","Social Anxiety Disorder","Panic Disorder","Specific Phobia"],
    "answer":"Panic Disorder"},
   {"id":"q052","text":"Cognitive Behavioral Therapy (CBT) targets:",
    "options":["Unconscious conflicts","Maladaptive thoughts and behaviors","Neurotransmitter imbalances","Early childhood experiences"],
    "answer":"Maladaptive thoughts and behaviors"},
   {"id":"q053","text":"Hallucinations and delusions are hallmark symptoms of:",
    "options":["Major Depressive Disorder","Borderline Personality Disorder","Schizophrenia","Obsessive-Compulsive Disorder"],
    "answer":"Schizophrenia"},
   {"id":"q054","text":"First-line pharmacological treatment for most anxiety disorders is:",
    "options":["Benzodiazepines","Antipsychotics","SSRIs","Mood stabilizers"],
    "answer":"SSRIs"}
 ]',
 5, 'APPROVED', '10000000-0000-0000-0000-000000000003',
 NOW() - INTERVAL '108 days', NOW() - INTERVAL '108 days'),

-- ── Abnormal Psychology — Quiz (Anxiety Disorders) ───────────
('60000000-0000-0000-0000-000000000006',
 'Anxiety Disorders — Quiz',
 'QUIZ', '30000000-0000-0000-0000-000000000003', '40000000-0000-0000-0000-000000000022',
 '[
   {"id":"q060","text":"GAD is characterized by excessive worry lasting at least:",
    "options":["2 weeks","1 month","6 months","1 year"],
    "answer":"6 months"},
   {"id":"q061","text":"The fear of specific objects or situations is classified as:",
    "options":["GAD","Panic Disorder","Specific Phobia","Agoraphobia"],
    "answer":"Specific Phobia"},
   {"id":"q062","text":"Systematic desensitization is a behavioral technique based on:",
    "options":["Operant conditioning","Classical conditioning","Observational learning","Cognitive restructuring"],
    "answer":"Classical conditioning"},
   {"id":"q063","text":"Which brain structure is hyperactive in anxiety disorders?",
    "options":["Hippocampus","Prefrontal cortex","Amygdala","Thalamus"],
    "answer":"Amygdala"},
   {"id":"q064","text":"Social Anxiety Disorder (SAD) involves fear of:",
    "options":["Open spaces","Social scrutiny and embarrassment","Specific objects","Recurring panic attacks"],
    "answer":"Social scrutiny and embarrassment"}
 ]',
 5, 'APPROVED', '10000000-0000-0000-0000-000000000003',
 NOW() - INTERVAL '98 days', NOW() - INTERVAL '98 days'),

-- ── Pending assessment (not yet approved) ────────────────────
('60000000-0000-0000-0000-000000000007',
 'Psychological Assessment — Pre-Assessment',
 'PRE_ASSESSMENT', '30000000-0000-0000-0000-000000000005', NULL,
 '[
   {"id":"q070","text":"Reliability in psychological testing refers to:",
    "options":["Whether a test measures what it claims to measure","Consistency of test scores","Cultural fairness","The range of norms available"],
    "answer":"Consistency of test scores"},
   {"id":"q071","text":"The MMPI-2 contains how many items?",
    "options":["373","467","567","640"],
    "answer":"567"},
   {"id":"q072","text":"A test''s ability to measure the construct it is intended to measure is called:",
    "options":["Reliability","Standardization","Validity","Norms"],
    "answer":"Validity"},
   {"id":"q073","text":"The Rorschach Inkblot Test is an example of which type of assessment?",
    "options":["Objective","Projective","Behavioral","Neuropsychological"],
    "answer":"Projective"},
   {"id":"q074","text":"Intelligence testing originated with work by:",
    "options":["Carl Jung","Alfred Binet","David Wechsler","Lewis Terman"],
    "answer":"Alfred Binet"}
 ]',
 5, 'PENDING', '10000000-0000-0000-0000-000000000003',
 NOW() - INTERVAL '6 days', NOW() - INTERVAL '6 days')
ON CONFLICT (id) DO NOTHING;


-- ────────────────────────────────────────────────────────────
-- 9. ASSESSMENT SUBMISSIONS
-- Spread across the last 60 days for realistic analytics
-- ────────────────────────────────────────────────────────────

-- student1 submissions
INSERT INTO assessment_submissions (id, assessment_id, student_id, score, passed, correct, total, answers, time_taken_s, submitted_at) VALUES
('70000000-0000-0000-0001-000000000001','60000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000011', 60, FALSE, 3, 5, '[]', 420, NOW() - INTERVAL '58 days'),
('70000000-0000-0000-0001-000000000002','60000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000011', 83.33, TRUE,  5, 6, '[]', 510, NOW() - INTERVAL '50 days'),
('70000000-0000-0000-0001-000000000003','60000000-0000-0000-0000-000000000003','10000000-0000-0000-0000-000000000011', 90, TRUE,  9, 10, '[]', 720, NOW() - INTERVAL '40 days'),
('70000000-0000-0000-0001-000000000004','60000000-0000-0000-0000-000000000004','10000000-0000-0000-0000-000000000011', 80, TRUE,  4, 5, '[]', 390, NOW() - INTERVAL '35 days'),
('70000000-0000-0000-0001-000000000005','60000000-0000-0000-0000-000000000005','10000000-0000-0000-0000-000000000011', 60, FALSE, 3, 5, '[]', 360, NOW() - INTERVAL '28 days'),
('70000000-0000-0000-0001-000000000006','60000000-0000-0000-0000-000000000006','10000000-0000-0000-0000-000000000011', 80, TRUE,  4, 5, '[]', 450, NOW() - INTERVAL '15 days'),

-- student2 submissions
('70000000-0000-0000-0002-000000000001','60000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000012', 80, TRUE,  4, 5, '[]', 390, NOW() - INTERVAL '55 days'),
('70000000-0000-0000-0002-000000000002','60000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000012', 66.67, FALSE, 4, 6, '[]', 480, NOW() - INTERVAL '48 days'),
('70000000-0000-0000-0002-000000000003','60000000-0000-0000-0000-000000000003','10000000-0000-0000-0000-000000000012', 80, TRUE,  8, 10, '[]', 690, NOW() - INTERVAL '38 days'),
('70000000-0000-0000-0002-000000000004','60000000-0000-0000-0000-000000000004','10000000-0000-0000-0000-000000000012', 100, TRUE, 5, 5, '[]', 300, NOW() - INTERVAL '30 days'),
('70000000-0000-0000-0002-000000000005','60000000-0000-0000-0000-000000000005','10000000-0000-0000-0000-000000000012', 80, TRUE,  4, 5, '[]', 420, NOW() - INTERVAL '20 days'),

-- student3 submissions
('70000000-0000-0000-0003-000000000001','60000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000013', 40, FALSE, 2, 5, '[]', 480, NOW() - INTERVAL '52 days'),
('70000000-0000-0000-0003-000000000002','60000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000013', 50, FALSE, 3, 6, '[]', 600, NOW() - INTERVAL '44 days'),
('70000000-0000-0000-0003-000000000003','60000000-0000-0000-0000-000000000003','10000000-0000-0000-0000-000000000013', 70, FALSE, 7, 10, '[]', 750, NOW() - INTERVAL '36 days'),
('70000000-0000-0000-0003-000000000004','60000000-0000-0000-0000-000000000004','10000000-0000-0000-0000-000000000013', 60, FALSE, 3, 5, '[]', 420, NOW() - INTERVAL '25 days'),

-- student4 submissions
('70000000-0000-0000-0004-000000000001','60000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000014', 100, TRUE, 5, 5, '[]', 350, NOW() - INTERVAL '50 days'),
('70000000-0000-0000-0004-000000000002','60000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000014', 100, TRUE, 6, 6, '[]', 440, NOW() - INTERVAL '42 days'),
('70000000-0000-0000-0004-000000000003','60000000-0000-0000-0000-000000000003','10000000-0000-0000-0000-000000000014', 100, TRUE, 10, 10, '[]', 660, NOW() - INTERVAL '34 days'),
('70000000-0000-0000-0004-000000000004','60000000-0000-0000-0000-000000000004','10000000-0000-0000-0000-000000000014', 80, TRUE,  4, 5, '[]', 370, NOW() - INTERVAL '22 days'),
('70000000-0000-0000-0004-000000000005','60000000-0000-0000-0000-000000000005','10000000-0000-0000-0000-000000000014', 100, TRUE, 5, 5, '[]', 330, NOW() - INTERVAL '10 days'),
('70000000-0000-0000-0004-000000000006','60000000-0000-0000-0000-000000000006','10000000-0000-0000-0000-000000000014', 100, TRUE, 5, 5, '[]', 350, NOW() - INTERVAL '3 days')
ON CONFLICT (id) DO NOTHING;


-- ────────────────────────────────────────────────────────────
-- 10. STUDENT PROGRESS  (content read completions)
-- ────────────────────────────────────────────────────────────
INSERT INTO student_progress (id, student_id, content_id, completed_at) VALUES
-- student1
('80000000-0000-0000-0001-000000000001','10000000-0000-0000-0000-000000000011','50000000-0000-0000-0000-000000000001', NOW() - INTERVAL '56 days'),
('80000000-0000-0000-0001-000000000002','10000000-0000-0000-0000-000000000011','50000000-0000-0000-0000-000000000002', NOW() - INTERVAL '52 days'),
('80000000-0000-0000-0001-000000000003','10000000-0000-0000-0000-000000000011','50000000-0000-0000-0000-000000000003', NOW() - INTERVAL '48 days'),
('80000000-0000-0000-0001-000000000004','10000000-0000-0000-0000-000000000011','50000000-0000-0000-0000-000000000005', NOW() - INTERVAL '33 days'),
-- student2
('80000000-0000-0000-0002-000000000001','10000000-0000-0000-0000-000000000012','50000000-0000-0000-0000-000000000001', NOW() - INTERVAL '53 days'),
('80000000-0000-0000-0002-000000000002','10000000-0000-0000-0000-000000000012','50000000-0000-0000-0000-000000000002', NOW() - INTERVAL '50 days'),
('80000000-0000-0000-0002-000000000003','10000000-0000-0000-0000-000000000012','50000000-0000-0000-0000-000000000003', NOW() - INTERVAL '45 days'),
('80000000-0000-0000-0002-000000000004','10000000-0000-0000-0000-000000000012','50000000-0000-0000-0000-000000000004', NOW() - INTERVAL '40 days'),
('80000000-0000-0000-0002-000000000005','10000000-0000-0000-0000-000000000012','50000000-0000-0000-0000-000000000005', NOW() - INTERVAL '28 days'),
('80000000-0000-0000-0002-000000000006','10000000-0000-0000-0000-000000000012','50000000-0000-0000-0000-000000000007', NOW() - INTERVAL '18 days'),
-- student3
('80000000-0000-0000-0003-000000000001','10000000-0000-0000-0000-000000000013','50000000-0000-0000-0000-000000000001', NOW() - INTERVAL '50 days'),
('80000000-0000-0000-0003-000000000002','10000000-0000-0000-0000-000000000013','50000000-0000-0000-0000-000000000003', NOW() - INTERVAL '42 days'),
-- student4
('80000000-0000-0000-0004-000000000001','10000000-0000-0000-0000-000000000014','50000000-0000-0000-0000-000000000001', NOW() - INTERVAL '48 days'),
('80000000-0000-0000-0004-000000000002','10000000-0000-0000-0000-000000000014','50000000-0000-0000-0000-000000000002', NOW() - INTERVAL '45 days'),
('80000000-0000-0000-0004-000000000003','10000000-0000-0000-0000-000000000014','50000000-0000-0000-0000-000000000003', NOW() - INTERVAL '40 days'),
('80000000-0000-0000-0004-000000000004','10000000-0000-0000-0000-000000000014','50000000-0000-0000-0000-000000000004', NOW() - INTERVAL '35 days'),
('80000000-0000-0000-0004-000000000005','10000000-0000-0000-0000-000000000014','50000000-0000-0000-0000-000000000005', NOW() - INTERVAL '30 days'),
('80000000-0000-0000-0004-000000000006','10000000-0000-0000-0000-000000000014','50000000-0000-0000-0000-000000000006', NOW() - INTERVAL '20 days'),
('80000000-0000-0000-0004-000000000007','10000000-0000-0000-0000-000000000014','50000000-0000-0000-0000-000000000007', NOW() - INTERVAL '8 days'),
('80000000-0000-0000-0004-000000000008','10000000-0000-0000-0000-000000000014','50000000-0000-0000-0000-000000000008', NOW() - INTERVAL '2 days')
ON CONFLICT (student_id, content_id) DO NOTHING;


-- ────────────────────────────────────────────────────────────
-- 11. ENROLLMENTS
-- ────────────────────────────────────────────────────────────
INSERT INTO enrollments (id, student_id, subject_id, status, enrolled_at) VALUES
-- student1 enrolled in 3 subjects
('90000000-0000-0000-0001-000000000001','10000000-0000-0000-0000-000000000011','30000000-0000-0000-0000-000000000001','ACTIVE', NOW() - INTERVAL '88 days'),
('90000000-0000-0000-0001-000000000002','10000000-0000-0000-0000-000000000011','30000000-0000-0000-0000-000000000002','ACTIVE', NOW() - INTERVAL '88 days'),
('90000000-0000-0000-0001-000000000003','10000000-0000-0000-0000-000000000011','30000000-0000-0000-0000-000000000003','ACTIVE', NOW() - INTERVAL '88 days'),
-- student2 enrolled in all 5 approved subjects
('90000000-0000-0000-0002-000000000001','10000000-0000-0000-0000-000000000012','30000000-0000-0000-0000-000000000001','ACTIVE', NOW() - INTERVAL '83 days'),
('90000000-0000-0000-0002-000000000002','10000000-0000-0000-0000-000000000012','30000000-0000-0000-0000-000000000002','ACTIVE', NOW() - INTERVAL '83 days'),
('90000000-0000-0000-0002-000000000003','10000000-0000-0000-0000-000000000012','30000000-0000-0000-0000-000000000003','ACTIVE', NOW() - INTERVAL '83 days'),
('90000000-0000-0000-0002-000000000004','10000000-0000-0000-0000-000000000012','30000000-0000-0000-0000-000000000004','ACTIVE', NOW() - INTERVAL '83 days'),
('90000000-0000-0000-0002-000000000005','10000000-0000-0000-0000-000000000012','30000000-0000-0000-0000-000000000005','ACTIVE', NOW() - INTERVAL '83 days'),
-- student3 enrolled in 2 subjects
('90000000-0000-0000-0003-000000000001','10000000-0000-0000-0000-000000000013','30000000-0000-0000-0000-000000000001','ACTIVE', NOW() - INTERVAL '78 days'),
('90000000-0000-0000-0003-000000000002','10000000-0000-0000-0000-000000000013','30000000-0000-0000-0000-000000000003','ACTIVE', NOW() - INTERVAL '78 days'),
-- student4 enrolled in all 5 approved subjects
('90000000-0000-0000-0004-000000000001','10000000-0000-0000-0000-000000000014','30000000-0000-0000-0000-000000000001','ACTIVE', NOW() - INTERVAL '73 days'),
('90000000-0000-0000-0004-000000000002','10000000-0000-0000-0000-000000000014','30000000-0000-0000-0000-000000000002','ACTIVE', NOW() - INTERVAL '73 days'),
('90000000-0000-0000-0004-000000000003','10000000-0000-0000-0000-000000000014','30000000-0000-0000-0000-000000000003','ACTIVE', NOW() - INTERVAL '73 days'),
('90000000-0000-0000-0004-000000000004','10000000-0000-0000-0000-000000000014','30000000-0000-0000-0000-000000000004','ACTIVE', NOW() - INTERVAL '73 days'),
('90000000-0000-0000-0004-000000000005','10000000-0000-0000-0000-000000000014','30000000-0000-0000-0000-000000000005','ACTIVE', NOW() - INTERVAL '73 days')
ON CONFLICT (student_id, subject_id) DO NOTHING;


-- ────────────────────────────────────────────────────────────
-- 12. ACTIVITY LOGS
-- ────────────────────────────────────────────────────────────
INSERT INTO activity_logs (id, user_id, action, target, target_id, ip_address, created_at) VALUES
('a0000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','User logged in','admin@ppri.edu','10000000-0000-0000-0000-000000000001','127.0.0.1', NOW() - INTERVAL '2 days'),
('a0000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000001','Updated system settings',NULL,NULL,'127.0.0.1', NOW() - INTERVAL '2 days'),
('a0000000-0000-0000-0000-000000000003','10000000-0000-0000-0000-000000000002','User logged in','faculty1@ppri.edu','10000000-0000-0000-0000-000000000002','127.0.0.1', NOW() - INTERVAL '5 days'),
('a0000000-0000-0000-0000-000000000004','10000000-0000-0000-0000-000000000002','Created content module','Introduction to Psychology: A Brief History','50000000-0000-0000-0000-000000000001','127.0.0.1', NOW() - INTERVAL '145 days'),
('a0000000-0000-0000-0000-000000000005','10000000-0000-0000-0000-000000000002','Created assessment','General Psychology — Pre-Assessment','60000000-0000-0000-0000-000000000001','127.0.0.1', NOW() - INTERVAL '138 days'),
('a0000000-0000-0000-0000-000000000006','10000000-0000-0000-0000-000000000001','Assessment approved','General Psychology — Pre-Assessment','60000000-0000-0000-0000-000000000001','127.0.0.1', NOW() - INTERVAL '137 days'),
('a0000000-0000-0000-0000-000000000007','10000000-0000-0000-0000-000000000011','User logged in','student1@ppri.edu','10000000-0000-0000-0000-000000000011','127.0.0.1', NOW() - INTERVAL '58 days'),
('a0000000-0000-0000-0000-000000000008','10000000-0000-0000-0000-000000000011','Assessment submitted','General Psychology — Pre-Assessment','60000000-0000-0000-0000-000000000001','127.0.0.1', NOW() - INTERVAL '58 days'),
('a0000000-0000-0000-0000-000000000009','10000000-0000-0000-0000-000000000014','User logged in','student4@ppri.edu','10000000-0000-0000-0000-000000000014','127.0.0.1', NOW() - INTERVAL '3 days'),
('a0000000-0000-0000-0000-000000000010','10000000-0000-0000-0000-000000000003','Submitted content for review','Psychological Assessment Tools: MMPI and Rorschach','50000000-0000-0000-0000-000000000010','127.0.0.1', NOW() - INTERVAL '7 days'),
('a0000000-0000-0000-0000-000000000011','10000000-0000-0000-0000-000000000003','Submitted assessment for review','Psychological Assessment — Pre-Assessment','60000000-0000-0000-0000-000000000007','127.0.0.1', NOW() - INTERVAL '6 days'),
('a0000000-0000-0000-0000-000000000012','10000000-0000-0000-0000-000000000001','Created subject','General Psychology','30000000-0000-0000-0000-000000000001','127.0.0.1', NOW() - INTERVAL '160 days')
ON CONFLICT (id) DO NOTHING;


-- ────────────────────────────────────────────────────────────
-- 13. SAMPLE REVISION REQUEST (faculty)
-- ────────────────────────────────────────────────────────────
INSERT INTO revisions (id, target_type, target_id, title, details, category, notes, status, created_by, created_at) VALUES
('b0000000-0000-0000-0000-000000000001',
 'MODULE', '50000000-0000-0000-0000-000000000003',
 'Update neuron diagrams and add myelination section',
 'The content on myelination is brief. Please add a section describing demyelinating diseases (e.g., MS) and their psychological impact.',
 'MODULE', '[]', 'PENDING',
 '10000000-0000-0000-0000-000000000002', NOW() - INTERVAL '10 days')
ON CONFLICT (id) DO NOTHING;


COMMIT;

-- ============================================================
-- Quick verification query (run manually after seeding)
-- ============================================================
-- SELECT 'roles'          AS tbl, COUNT(*) FROM roles
-- UNION ALL SELECT 'users',           COUNT(*) FROM users
-- UNION ALL SELECT 'whitelist',        COUNT(*) FROM whitelist
-- UNION ALL SELECT 'subjects',         COUNT(*) FROM subjects
-- UNION ALL SELECT 'topics',           COUNT(*) FROM topics
-- UNION ALL SELECT 'content_modules',  COUNT(*) FROM content_modules
-- UNION ALL SELECT 'assessments',      COUNT(*) FROM assessments
-- UNION ALL SELECT 'submissions',      COUNT(*) FROM assessment_submissions
-- UNION ALL SELECT 'progress',         COUNT(*) FROM student_progress
-- UNION ALL SELECT 'enrollments',      COUNT(*) FROM enrollments
-- UNION ALL SELECT 'activity_logs',    COUNT(*) FROM activity_logs;