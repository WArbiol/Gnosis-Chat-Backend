-- Add is_pinned column to conversations table
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN DEFAULT FALSE;

-- Index to optimize ordering by pinned conversations
CREATE INDEX IF NOT EXISTS idx_conversations_user_pinned ON conversations(user_id, is_pinned DESC, updated_at DESC);
