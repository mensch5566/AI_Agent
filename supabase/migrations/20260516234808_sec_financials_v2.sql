-- SEC Financials v2 schema (clean rebuild)
-- Spec: tmp/financials-viewer-redesign-plan.md §20 (v5.1)
-- Dictionary: docs/sec-financials-v2-schema.md
-- Behavior rules: docs/financials-data-rules.md (SEC v2 section)
--
-- This migration:
--   1. DROPs legacy `financial_*` tables (user authorized clean rebuild,
--      no data to preserve — only 1-2 tickers ingested in early format).
--   2. CREATEs 5 new `sec_financial_*` tables for US SEC pipeline.
--
-- US-only scope. TWSE pipeline does NOT use these tables.

-- ============================================================================
-- 1. DROP legacy tables (clean slate per user authorization 2026-05-16)
-- ============================================================================

DROP TABLE IF EXISTS financial_supplement CASCADE;
DROP TABLE IF EXISTS financial_metrics CASCADE;
DROP TABLE IF EXISTS financial_facts CASCADE;
DROP TABLE IF EXISTS financial_companies CASCADE;

-- ============================================================================
-- 2. sec_financial_companies — one row per ticker
-- ============================================================================

CREATE TABLE sec_financial_companies (
  ticker                 text PRIMARY KEY,
  company_name           text NOT NULL,
  exchange               text NOT NULL,
  cik                    text NOT NULL,
  currency               text NOT NULL DEFAULT 'USD',
  fiscal_year_end_month  smallint NOT NULL DEFAULT 12,
  filings                jsonb NOT NULL,         -- {Qx_FYyyyy: {form, period_end, accession_number, primary_doc}, ...}
  sign_flip_concepts     jsonb NOT NULL DEFAULT '[]'::jsonb,  -- array of XBRL concept strings with negatedLabel role
  last_updated           timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE sec_financial_companies IS 'SEC v2: per-ticker metadata + filings index + display-sign-flip concept list.';
COMMENT ON COLUMN sec_financial_companies.sign_flip_concepts IS 'XBRL concepts that should be displayed with parentheses (negative) at render time; XBRL stores positive magnitude.';

-- ============================================================================
-- 3. sec_financial_facts — direct disclosed facts only (GAAP + NON_GAAP)
-- ============================================================================

CREATE TABLE sec_financial_facts (
  cell_id            text PRIMARY KEY,           -- deterministic SHA-256 hash; see _shared/cell_id.py
  ticker             text NOT NULL,
  period             text NOT NULL,              -- Qx_FYyyyy / FYyyyy / NM_FYyyyy
  period_start       date,
  period_end         date NOT NULL,
  period_kind        text NOT NULL,
  statement          text NOT NULL,              -- IS | BS | CF | RATIO
  version            text NOT NULL,              -- GAAP | NON_GAAP
  uni_account        text NOT NULL,              -- canonical key per docs/sec-financials-v2-schema.md
  source_account     text NOT NULL,              -- PDF label / XBRL concept name as-reported
  xbrl_tag           text,                       -- us-gaap:Revenues (GAAP); null for NON_GAAP or synthesized rows
  value              numeric NOT NULL,           -- canonical unit value (direct facts MUST have value)
  weight             smallint NOT NULL,          -- XBRL calculation weight (+1 / -1)
  unit               text NOT NULL,              -- USD_thousands / USD_millions / USD_per_share / millions_shares / Pure / etc.
  status             text NOT NULL DEFAULT 'SOURCE_OF_TRUTH',
  ordinal            smallint,                   -- presentation order
  long_tail_metadata jsonb,                      -- {rolls_up_to, is_recurring, last_occurrence_date} for long-tail bucket rows
  provenance         jsonb NOT NULL,             -- {source_filing, accession_number, audit_source}
  last_updated       timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT sff_status_check CHECK (status = 'SOURCE_OF_TRUTH'),
  CONSTRAINT sff_version_check CHECK (version IN ('GAAP', 'NON_GAAP')),
  CONSTRAINT sff_statement_check CHECK (statement IN ('IS', 'BS', 'CF', 'RATIO')),
  CONSTRAINT sff_period_kind_check CHECK (
    period_kind IN ('quarter_duration', 'fy_annual_duration', 'ytd_duration', 'instant_period_end')
  ),
  CONSTRAINT sff_statement_period_kind_check CHECK (
    (statement = 'BS' AND period_kind = 'instant_period_end')
    OR (statement IN ('IS', 'CF', 'RATIO') AND period_kind IN ('quarter_duration', 'fy_annual_duration', 'ytd_duration'))
  )
);

CREATE UNIQUE INDEX sff_identity ON sec_financial_facts
  (ticker, period, period_kind, version, statement, uni_account, source_account, COALESCE(xbrl_tag, ''));
CREATE INDEX sff_ticker_period ON sec_financial_facts (ticker, period);
CREATE INDEX sff_ticker_stmt_ver ON sec_financial_facts (ticker, statement, version);

COMMENT ON TABLE sec_financial_facts IS 'SEC v2: direct disclosed consolidated facts only. Q4 single-quarter IS/CF derived values go to sec_financial_metrics. Disclosed ratios (8-K) use statement=RATIO.';

-- ============================================================================
-- 4. sec_financial_metrics — derived values (Q4 reconstruction, margins, etc.)
-- ============================================================================

CREATE TABLE sec_financial_metrics (
  cell_id      text PRIMARY KEY,
  ticker       text NOT NULL,
  period       text NOT NULL,
  period_start date,
  period_end   date NOT NULL,
  period_kind  text NOT NULL,                    -- can include derived_q4 (metrics-only)
  statement    text NOT NULL,
  version      text NOT NULL,
  uni_account  text NOT NULL,
  value        numeric NOT NULL,                 -- derived rows MUST have value; NOT_DISCLOSED is NOT persisted
  unit         text NOT NULL,
  status       text NOT NULL,
  provenance   jsonb NOT NULL,                   -- {formula, inputs: [cell_id, ...], exclusion_rule, audit_source}
  last_updated timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT sfm_status_check CHECK (status IN ('DERIVED_FROM_DISCLOSED', 'EXCLUDED_FROM_NONGAAP')),
  CONSTRAINT sfm_version_check CHECK (version IN ('GAAP', 'NON_GAAP')),
  CONSTRAINT sfm_statement_check CHECK (statement IN ('IS', 'BS', 'CF', 'RATIO')),
  CONSTRAINT sfm_period_kind_check CHECK (
    period_kind IN ('quarter_duration', 'fy_annual_duration', 'ytd_duration', 'instant_period_end', 'derived_q4')
  )
);

CREATE UNIQUE INDEX sfm_identity ON sec_financial_metrics
  (ticker, period, period_kind, version, statement, uni_account);
CREATE INDEX sfm_ticker_period ON sec_financial_metrics (ticker, period);

COMMENT ON TABLE sec_financial_metrics IS 'SEC v2: all derived values. derive-analytics MUST NOT overwrite sec_financial_facts: SELECT facts WHERE same key, skip if exists.';

-- ============================================================================
-- 5. sec_financial_dimensional_facts — segment / geography / customer concentration
-- ============================================================================

CREATE TABLE sec_financial_dimensional_facts (
  cell_id               text PRIMARY KEY,
  ticker                text NOT NULL,
  period                text NOT NULL,
  period_start          date,
  period_end            date NOT NULL,
  period_kind           text NOT NULL,
  axis                  text NOT NULL,           -- product / geography / customer_concentration / business_segment
  axis_qname            text,                    -- nullable: NLM fallback path may lack qname
  axis_key              text NOT NULL,           -- axis_qname OR 'local:' + normalize_axis_label(axis)
  member                text NOT NULL,           -- raw PDF label (display only)
  member_qname          text,                    -- nullable for NLM fallback
  member_key            text NOT NULL,           -- member_qname OR 'local:' + normalize_member_label(member)
  source_account        text NOT NULL,           -- mirrors member for backward parity with parse output
  source_account_qname  text,
  source_doc            text,                    -- instance_doc_xbrl / 8K_table / 10Q_note
  uni_account           text NOT NULL,           -- revenue / revenue_pct_of_total / long_lived_assets / etc.
  value                 numeric NOT NULL,
  unit                  text NOT NULL,
  decimals              smallint,                -- XBRL decimals attribute (smaller / more positive = more precise for negative range)
  other_dimensions      jsonb,                   -- [{axis, member}, ...] for multi-axis intersections
  provenance            jsonb NOT NULL,          -- {sources: [{source_filing, accession_number, source_doc, raw_member_label}], precision_dedupe?, audit_source}
  last_updated          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT sfdf_period_kind_check CHECK (
    period_kind IN ('quarter_duration', 'fy_annual_duration', 'ytd_duration', 'instant_period_end')
  )
);

CREATE UNIQUE INDEX sfdf_identity ON sec_financial_dimensional_facts
  (ticker, period, period_kind, axis_key, member_key, uni_account, COALESCE(other_dimensions::text, ''));
CREATE INDEX sfdf_ticker_axis ON sec_financial_dimensional_facts (ticker, axis);
CREATE INDEX sfdf_other_dims_gin ON sec_financial_dimensional_facts USING gin (other_dimensions);

COMMENT ON TABLE sec_financial_dimensional_facts IS 'SEC v2: segment / geo / customer dimensional disclosures. Distinct grain from consolidated facts. member_key handles label variants (Data Center ↔ Datacenter).';

-- ============================================================================
-- 6. sec_financial_edges — XBRL calc / presentation / def_linkbase
-- ============================================================================

CREATE TABLE sec_financial_edges (
  edge_id         text PRIMARY KEY,
  ticker          text NOT NULL,
  period          text NOT NULL,
  edge_type       text NOT NULL,                 -- calc | presentation | def_dim
  role_uri        text NOT NULL,
  parent_qname    text,                          -- nullable for root edges
  child_qname     text NOT NULL,
  weight          smallint,                      -- calc edge only
  ordinal         numeric,                       -- presentation order
  preferred_label text,
  last_updated    timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT sfe_edge_type_check CHECK (edge_type IN ('calc', 'presentation', 'def_dim'))
);

-- Same parent-child can appear multiple times in a presentation role
-- with different preferred_label (e.g. periodStartLabel / periodEndLabel)
-- and different ordinals — include both in identity.
CREATE UNIQUE INDEX sfe_identity ON sec_financial_edges
  (ticker, period, edge_type, role_uri,
   COALESCE(parent_qname, ''), child_qname,
   COALESCE(preferred_label, ''), COALESCE(ordinal::text, ''));
CREATE INDEX sfe_ticker_type ON sec_financial_edges (ticker, edge_type);

COMMENT ON TABLE sec_financial_edges IS 'SEC v2: XBRL structural knowledge (calc / presentation / dimension hierarchies). Not for Viewer display; used for anchor audit + future wiki ingest.';
