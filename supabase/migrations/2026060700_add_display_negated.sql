-- Add PDF-faithful sign flag to facts. When the matched XBRL presentation arc's
-- preferred_label role is a "negated…" role (negatedLabel / negatedTerseLabel /
-- negatedTotalLabel / negatedNetLabel / negatedPeriodStart|EndLabel), the PDF
-- renders -storedValue (TRUE negation). The frontend reads this flag and applies
-- `display_negated ? -value : value` before formatting. Resolved at upsert from
-- the SAME matched edge that yields display_label + ordinal (lockstep). Nullable
-- (null => ticker not yet re-upserted => frontend falls back to legacy
-- sign_flip_concepts behavior). Display metadata only — NOT part of the fact
-- identity key, so no dedupe/identity impact.
alter table public.sec_financial_facts
  add column if not exists display_negated boolean;

comment on column public.sec_financial_facts.display_negated is
  'PDF-faithful sign flag resolved at upsert from the matched presentation arc preferred_label "negated…" role; true => frontend renders -value (TRUE negation); null => legacy sign_flip_concepts fallback';

-- rollback:
-- alter table public.sec_financial_facts drop column if exists display_negated;
