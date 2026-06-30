-- =============================================================
-- Migration 001: Conversations, Messages, Citations
-- Run in Supabase SQL Editor (Dashboard > SQL Editor)
-- =============================================================

-- conversations
CREATE TABLE conversations (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  title       TEXT NOT NULL DEFAULT 'Nova conversa',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_conversations_user_updated ON conversations(user_id, updated_at DESC);

CREATE TRIGGER trg_conversations_updated_at
  BEFORE UPDATE ON conversations
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- messages
CREATE TABLE messages (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content         TEXT NOT NULL,
  route           TEXT DEFAULT '',
  token_count     INT DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_messages_conv_created ON messages(conversation_id, created_at);

-- citations
CREATE TABLE citations (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id  UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  pdf_name    TEXT NOT NULL,
  page        INT NOT NULL,
  snippet     TEXT NOT NULL DEFAULT '',
  chunk_id    TEXT DEFAULT '',
  sort_order  SMALLINT DEFAULT 0
);
CREATE INDEX idx_citations_message ON citations(message_id);

-- RLS (reusa auth.uid() do Supabase)
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_conversations" ON conversations FOR ALL USING (user_id = auth.uid());

ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_messages" ON messages FOR ALL
  USING (conversation_id IN (SELECT id FROM conversations WHERE user_id = auth.uid()));

ALTER TABLE citations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_citations" ON citations FOR ALL
  USING (message_id IN (SELECT id FROM messages WHERE conversation_id IN (
    SELECT id FROM conversations WHERE user_id = auth.uid()
  )));
