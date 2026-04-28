# AI_Agent Architecture

Updated: 2026-04-15

## Purpose

`AI_Agent` is an internal multi-tool workspace centered on a portal UI. It combines:
- portal-style navigation
- equity financial analysis
- research workflows and news curation
- reusable AI skills and supporting docs

The repo is no longer a single-purpose prototype. New features should be placed into an existing module when possible, and new data flows should be documented here and in `docs/STATUS.md`.

## Top-Level Structure

### `app/`
Next.js App Router frontend and API routes.

Main areas:
- `app/page.tsx`
  - Portal homepage and top-level navigation
- `app/financials/`
  - Financials Viewer UI
  - Includes financial statements, ratios, segments, non-GAAP, and valuation views
- `app/api/financials/`
  - Financial facts API for the Financials Viewer
- `app/api/valuation/`
  - Historical valuation API for TTM P/E charting

### `app/components/financials/`
Reusable UI and data-formatting logic for the Financials Viewer.

Examples:
- table renderers
- ratio/segment panels
- valuation chart client component
- local financial formatting rules

### `lib/`
Server-side utility logic and data adapters.

Current example:
- `lib/valuation/peHistory.ts`
  - Fetches Yahoo historical prices and quarterly EPS
  - Reconstructs historical TTM EPS
  - Produces raw timeseries for frontend valuation charting

### `public/data/`
Static or generated research-oriented data artifacts used by internal pages.

This area currently mixes:
- equity research JSON
- weekly data artifacts

If this grows further, it should be split by domain and generation source.

### `Tools/`
Research, parsing, and pipeline tooling.

This is the workflow/tooling layer rather than the app runtime layer.

Examples:
- SEC parsing
- TWSE parsing
- news pipeline
- supplemental financial workflows

### `docs/`
Project operating docs and source-of-truth notes.

Current intent:
- `STATUS.md`
  - current state, shipped features, active gaps, next steps
- `ARCHITECTURE.md`
  - module boundaries and data flow
- feature-specific notes as needed

## Main Product Modules

### 1. Portal
Entry surface for internal tools.

Responsibilities:
- provide a single homepage for navigation
- expose major tool entrypoints without duplicating pages

Rule:
- if a new feature naturally belongs inside an existing page, prefer extending that page over adding another top-level portal card immediately

### 2. Financials Viewer
Primary equity-analysis UI.

Responsibilities:
- display normalized financial statements
- present ratios and segment breakdowns
- provide a valuation view for historical TTM P/E

Current data split:
- financial statement tabs:
  - depend on existing financial data pipeline and app-side `FactStore`
- valuation tab:
  - currently depends on Yahoo price history plus reconstructed quarterly EPS

This split is acceptable for now, but it is a known architectural inconsistency.

### 3. Research Workflows
Operational tooling for weekly research, news selection, and document generation.

Responsibilities:
- collect and filter candidate news
- generate weekly-summary style notes
- support reusable workflows through skills rather than only session memory

These workflows are partly inside this repo and partly shared through global AI config / skills.

## Data Flows

### Financial Statements Flow
1. external parsing or normalized data pipeline writes financial facts
2. frontend fetches financial API
3. app-side store normalizes view mode and display logic
4. viewer renders statements, ratios, segments, non-GAAP

### Valuation Flow
1. frontend requests `/api/valuation/[ticker]`
2. server fetches Yahoo price history and quarterly financial fundamentals
3. server reconstructs TTM EPS from rolling four-quarter EPS
4. server returns raw daily series with aligned TTM EPS
5. frontend resamples to day / month / quarter and computes moving averages

Important rule:
- historical TTM P/E is only valid when rolling four-quarter EPS exists
- no synthetic fallback should masquerade as historical TTM P/E

## Documentation Rules

### `docs/STATUS.md`
Use for:
- current state
- what shipped
- what is in progress
- known gaps and risks

### `docs/ARCHITECTURE.md`
Use for:
- module boundaries
- ownership and integration logic
- current data sources and flows
- structural decisions that should survive individual sessions

## Current Architectural Gaps

- financial statements and valuation are still backed by different upstream sources
- no formal test coverage for valuation API and reconstruction logic yet
- workflow tooling and app runtime live in the same repo but are not yet cleanly separated by domain ownership
- static/generated data under `public/data/` needs clearer lifecycle definition

## Near-Term Direction

- keep `portal` as the single entry surface
- keep `Financials Viewer` as the main equity workspace instead of splitting duplicate pages
- formalize status updates through `docs/STATUS.md`
- document structural changes here whenever a new module or data source is introduced
