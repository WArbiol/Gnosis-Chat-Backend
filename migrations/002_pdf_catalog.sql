-- =============================================================
-- Migration 002: PDF Catalog for Citations
-- Run in Supabase SQL Editor (Dashboard > SQL Editor)
-- =============================================================

CREATE TABLE pdf_catalog (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_name       TEXT NOT NULL UNIQUE,
  file_path       TEXT NOT NULL,
  chamber         INT NOT NULL DEFAULT 1 CHECK (chamber IN (1, 2)),
  author          TEXT DEFAULT 'Desconhecido',
  file_size_bytes BIGINT DEFAULT 0,
  page_count      INT DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_pdf_catalog_book_name ON pdf_catalog(book_name);

-- Enable RLS
ALTER TABLE pdf_catalog ENABLE ROW LEVEL SECURITY;

-- Allow authenticated users to read pdf_catalog
CREATE POLICY "Allow authenticated users to read pdf_catalog" ON pdf_catalog
  FOR SELECT TO authenticated USING (true);
