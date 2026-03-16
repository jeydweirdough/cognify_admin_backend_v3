-- ============================================================
-- Migration: add_announcements.sql
-- Creates the announcements table for admin-authored
-- notifications and TOS alignment progress updates.
--
-- Run this once against your Supabase database.
-- ============================================================

CREATE TABLE IF NOT EXISTS announcements (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    title         VARCHAR(200) NOT NULL,
    body          TEXT         NOT NULL,
    type          VARCHAR(30)  NOT NULL DEFAULT 'INFO',   -- INFO | WARNING | SUCCESS | TOS_PROGRESS
    audience      VARCHAR(20)  NOT NULL DEFAULT 'ALL',    -- ALL | ADMIN | FACULTY
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    tos_progress  INT          CHECK (tos_progress IS NULL OR (tos_progress >= 0 AND tos_progress <= 100)),
    expires_at    TIMESTAMPTZ,
    created_by    UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_announcements_active     ON announcements(is_active);
CREATE INDEX IF NOT EXISTS idx_announcements_created_at ON announcements(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_announcements_audience   ON announcements(audience);
