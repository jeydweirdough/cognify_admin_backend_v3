-- ============================================================
-- add_student_sessions.sql  —  Cognify
--
-- Adds a persistent study session / to-do table for students.
-- Run this migration AFTER schema_changes.sql has been applied.
-- Safe to re-run (CREATE TABLE IF NOT EXISTS).
-- ============================================================

CREATE TABLE IF NOT EXISTS student_sessions (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       VARCHAR(300) NOT NULL,
    subject     VARCHAR(200),
    session_date DATE        NOT NULL,
    start_time  VARCHAR(20),
    end_time    VARCHAR(20),
    completed   BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_student_sessions_user    ON student_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_student_sessions_date    ON student_sessions(user_id, session_date);
CREATE INDEX IF NOT EXISTS idx_student_sessions_completed ON student_sessions(user_id, completed);

-- ============================================================
-- Patch: ensure STUDENT role has mobile_add_session permission
-- Run this in your Supabase SQL editor
-- Safe to run multiple times (idempotent)
-- ============================================================

UPDATE roles
SET permissions = permissions || '["mobile_add_session"]'::jsonb
WHERE name = 'STUDENT'
  AND NOT (permissions @> '"mobile_add_session"'::jsonb);

-- Verify
SELECT name, permissions
FROM roles
WHERE name = 'STUDENT';

-- ============================================================
-- Patch: ensure STUDENT role has all session permissions
-- Run this in your Supabase SQL editor.
-- Safe to run multiple times (idempotent).
-- ============================================================

UPDATE roles
SET permissions = permissions
    || '["mobile_add_session","mobile_edit_session","mobile_delete_session"]'::jsonb
WHERE name = 'STUDENT'
  AND NOT (permissions @> '"mobile_add_session"'::jsonb);

-- If mobile_add_session already exists but the new ones are missing, add just those
UPDATE roles
SET permissions = permissions
    || '["mobile_edit_session","mobile_delete_session"]'::jsonb
WHERE name = 'STUDENT'
  AND (permissions @> '"mobile_add_session"'::jsonb)
  AND NOT (permissions @> '"mobile_edit_session"'::jsonb);

-- Verify
SELECT name, permissions
FROM roles
WHERE name = 'STUDENT';