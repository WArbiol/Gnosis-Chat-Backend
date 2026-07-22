-- =============================================================
-- Migration 005: Add suggested_followups JSONB column to messages table
-- Run in Supabase SQL Editor (Dashboard > SQL Editor)
-- =============================================================

ALTER TABLE messages ADD COLUMN IF NOT EXISTS suggested_followups JSONB DEFAULT '[]'::jsonb;
