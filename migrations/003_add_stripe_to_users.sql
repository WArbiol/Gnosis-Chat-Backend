-- =============================================================
-- Migration 003: Add Stripe columns to public.users table
-- Run in Supabase SQL Editor or migration runner
-- =============================================================

ALTER TABLE public.users
  ADD COLUMN stripe_customer_id TEXT UNIQUE,
  ADD COLUMN stripe_subscription_id TEXT UNIQUE,
  ADD COLUMN subscription_status TEXT DEFAULT 'free',
  ADD COLUMN current_period_end TIMESTAMPTZ;

-- Índices para buscas rápidas durante webhooks do Stripe
CREATE INDEX idx_users_stripe_customer_id ON public.users(stripe_customer_id);
CREATE INDEX idx_users_stripe_subscription_id ON public.users(stripe_subscription_id);
