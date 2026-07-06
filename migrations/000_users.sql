-- =============================================================
-- Migration 000: Users table (public schema)
-- Run in Supabase SQL Editor (Dashboard > SQL Editor)
-- =============================================================

-- Tabela pública de perfis (espelha auth.users com campos custom)
CREATE TABLE public.users (
  id             UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email          TEXT NOT NULL,
  display_name   TEXT DEFAULT '',
  avatar_url     TEXT DEFAULT '',
  plan           TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'basic', 'premium')),
  chamber_level  INT NOT NULL DEFAULT 1 CHECK (chamber_level IN (1, 2)),
  question_count INT NOT NULL DEFAULT 0,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índice para lookup por email
CREATE INDEX idx_users_email ON public.users(email);

-- Trigger: auto-atualiza updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Trigger: auto-cria perfil quando novo user se registra via Auth
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, email, display_name, avatar_url)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', ''),
    COALESCE(NEW.raw_user_meta_data->>'avatar_url', NEW.raw_user_meta_data->>'picture', '')
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- RLS: cada user vê/edita apenas seu próprio perfil
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own profile"
  ON public.users FOR SELECT USING (id = auth.uid());

CREATE POLICY "Users can update own profile"
  ON public.users FOR UPDATE USING (id = auth.uid());
