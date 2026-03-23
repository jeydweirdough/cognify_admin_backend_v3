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
  '["view_admin_dashboard","view_subjects","create_subjects","edit_subjects","delete_subjects","view_content","create_content","edit_content","delete_content","view_verification","approve_verification","reject_verification","view_assessments","create_assessments","edit_assessments","delete_assessments","resolve_revisions","view_analytics","view_student_analytics","view_users","create_users","edit_users","delete_users","approve_users","view_students_nav","view_students","create_students","edit_students","delete_students","approve_pending_students","view_whitelist","add_whitelist","edit_whitelist","delete_whitelist","cross_check_whitelist","students_whitelist_only","view_roles","manage_roles","view_logs","view_settings","edit_settings","manage_backup","import_settings","view_tos","create_tos","edit_tos","delete_tos","web_login"]'::jsonb,
  TRUE, NOW()
),

-- FACULTY — scoped; no TOS, no delete_*, no admin user-mgmt, roles, security, settings
(
  '00000000-0000-0000-0000-000000000002',
  'FACULTY',
  '["view_faculty_dashboard","view_subjects","create_subjects","edit_subjects","view_content","create_content","edit_content","view_verification","approve_verification","reject_verification","view_assessments","create_assessments","edit_assessments","view_analytics","view_student_analytics","view_students_nav","view_students","create_students","edit_students","view_whitelist","add_whitelist","edit_whitelist","cross_check_whitelist","students_whitelist_only","web_login","can_signup"]'::jsonb,
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
    registration_type, added_by, approved_by, approved_at,
    photo_avatar, avatar_index
) VALUES
(
  '10000000-0000-0000-0000-000000000001',
  'ADMIN-001','Ana','Cruz','Reyes','admin@cvsu.edu.ph',
  '$2b$12$KIXbhELtNrGF7JK7CzIxiONH5V7M3G0GzGPHMK5JxGmE0s0P2yOZC',
  '00000000-0000-0000-0000-000000000001','ACTIVE','Administration',
  NOW()-INTERVAL '180 days','MANUALLY_ADDED',NULL,NULL,NULL,
  NULL, NULL
),
(
  '10000000-0000-0000-0000-000000000002',
  'FAC-2024-001','Marco','Antonio','Santos','faculty1@cvsu.edu.ph',
  '$2b$12$X8RhYvBn7MtK3O4P5qAh8eP2Z3KMQd9hW1aJlH4yNxVRmUxS1sOaC',
  '00000000-0000-0000-0000-000000000002','ACTIVE','Developmental Psychology',
  NOW()-INTERVAL '150 days','MANUALLY_ADDED',
  '10000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000001',
  NOW()-INTERVAL '150 days',
  NULL, NULL
),
(
  '10000000-0000-0000-0000-000000000003',
  'FAC-2024-002','Elena','Grace','Villanueva','faculty2@cvsu.edu.ph',
  '$2b$12$X8RhYvBn7MtK3O4P5qAh8eP2Z3KMQd9hW1aJlH4yNxVRmUxS1sOaC',
  '00000000-0000-0000-0000-000000000002','ACTIVE','Clinical Psychology',
  NOW()-INTERVAL '120 days','MANUALLY_ADDED',
  '10000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000001',
  NOW()-INTERVAL '120 days',
  NULL, NULL
),
(
  '10000000-0000-0000-0000-000000000011',
  '2024-PSY-001','Jose','Miguel','Garcia','student1@cvsu.edu.ph',
  '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
  '00000000-0000-0000-0000-000000000003','ACTIVE','BS Psychology',
  NOW()-INTERVAL '90 days','SELF_REGISTERED',NULL,
  '10000000-0000-0000-0000-000000000001',NOW()-INTERVAL '88 days',
  'https://cxsymbqsleaiemekojhp.supabase.co/storage/v1/object/public/profiles/system/presets/preset_0.png', 0
),
(
  '10000000-0000-0000-0000-000000000012',
  '2024-PSY-002','Maria','Luisa','Fernandez','student2@cvsu.edu.ph',
  '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
  '00000000-0000-0000-0000-000000000003','ACTIVE','BS Psychology',
  NOW()-INTERVAL '85 days','SELF_REGISTERED',NULL,
  '10000000-0000-0000-0000-000000000001',NOW()-INTERVAL '83 days',
  'https://cxsymbqsleaiemekojhp.supabase.co/storage/v1/object/public/profiles/system/presets/preset_1.png', 1
),
-- Pre-created; no password yet (hasn't signed up)
(
  '10000000-0000-0000-0000-000000000015',
  '2024-PSY-005','Diego','Luis','Bautista','student5@cvsu.edu.ph',
  NULL,
  '00000000-0000-0000-0000-000000000003','ACTIVE','BS Psychology',
  NOW()-INTERVAL '5 days','MANUALLY_ADDED',
  '10000000-0000-0000-0000-000000000001',NULL,NULL,
  'https://cxsymbqsleaiemekojhp.supabase.co/storage/v1/object/public/profiles/system/presets/preset_4.png', 4
),
-- Self-registered (has password) but awaiting approval → PENDING
(
  '10000000-0000-0000-0000-000000000016',
  '2024-PSY-006','Sofia','Marie','Dela Cruz','student6@cvsu.edu.ph',
  '$2b$12$YmN9Z4K1pT7vL2o3Qw8e5u9R6Y0xH3fA1bD2cE5jG8kL0nM7pQ4rS6',
  '00000000-0000-0000-0000-000000000003','ACTIVE','BS Psychology',
  NOW()-INTERVAL '2 days', 'SELF_REGISTERED',NULL,NULL,NULL,
  'https://cxsymbqsleaiemekojhp.supabase.co/storage/v1/object/public/profiles/system/presets/preset_5.png', 5
)
ON CONFLICT (id) DO NOTHING;

-- ── 10. Activity Logs ─────────────────────────────────────────
INSERT INTO activity_logs (id, user_id, action, target, ip_address, created_at) VALUES
(gen_random_uuid(),'10000000-0000-0000-0000-000000000001', 'User logged in',         'admin@cvsu.edu.ph',                        '127.0.0.1',NOW()-INTERVAL '2 hours')
ON CONFLICT DO NOTHING;

COMMIT;