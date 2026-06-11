-- Add PDF-faithful display label to facts. Presentation ORDER reuses the existing
-- `ordinal smallint` column (added 20260516234808). display_label is nullable
-- (frontend falls back to source_account when null). Display metadata only — NOT
-- part of the fact identity key, so no dedupe/identity impact.
alter table public.sec_financial_facts
  add column if not exists display_label text;

comment on column public.sec_financial_facts.display_label is
  'PDF-faithful line label resolved at upsert from labels.json preferred_label role; null => frontend falls back to source_account';

-- rollback:
-- alter table public.sec_financial_facts drop column if exists display_label;
