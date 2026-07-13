-- Adiciona provedor da assinatura (stripe, apple, google, revenuecat)
ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS subscription_provider TEXT;
