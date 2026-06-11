# Runbook — Financials Viewer (Ship / Observe)

Operational runbook for the `app/financials/` PDF-faithful statement view + the
SEC financials data pipeline. Closes the SOP §3.6 (Ship: reversibility) and
§3.7 (Observe: synthetic monitoring) gates. Tier: **T3**.

---

## 1. Deploy / Release

- **Mechanism**: push to `main` → Vercel auto-builds + deploys production (GitHub
  integration). Frontend reads the existing production Supabase; DB migrations
  (`supabase/migrations/`) are applied separately and are forward-only + nullable,
  so a frontend deploy never needs a coordinated DB change.
- **Pre-merge gate** (already enforced): TDD green (`pytest` + `vitest` + `tsc`),
  multi-AI adversarial review (T3), human authorization for any production
  `--apply` write.

## 2. Rollback (reversibility — P7)

The change is display-layer over already-correct data, so rollback is cheap.
Two independent paths, fastest first:

1. **Vercel Instant Rollback** (no code, ~seconds): Vercel dashboard → project →
   Deployments → pick the last known-good production deployment → **Promote to
   Production**. Decouples release from the bad deploy without a git change.
2. **git revert** (source of truth): `git revert <merge-sha>` on `main` → push →
   Vercel redeploys the reverted tree. Use when the issue is in code that should
   leave `main` for good.
3. **Data rollback** (rare — only if a bad `--apply` re-upsert corrupted DB):
   re-run the upsert from a backed-up facts JSON (every re-parse writes a
   `*.backup-<date>.json` next to the canonical), or re-derive + re-upsert the
   affected ticker. `cell_id` is stable so re-upsert is in-place.

> **Deviation (honest)**: there is no per-feature flag for "As Reported" mode —
> reversibility relies on the two rollback paths above, not on toggling the
> feature off in place. Acceptable because the blast radius is display-only and
> both rollbacks are fast; revisit if the feature set grows enough to want
> independent kill-switches.

## 3. Synthetic monitoring (QA in production — P9)

`scripts/synthetic_check_financials.py` queries production Supabase (read-only)
and asserts, for every `KNOWN_TICKER`, the invariants the upsert gate enforces
at write time — so a silent regression (a re-upsert that drops the dedup pass, a
manual edit that breaks the position contract, a ticker gone empty) is caught
here, not by a user.

Checks:
- **A. Coverage / position** — a display-eligible row (display_label set) in
  IS/BS/CF for a displayed (non-YTD) period must carry an ordinal.
- **B. Dedup intact** — the rows the dedup pass suppresses (SNDK divestiture
  prose, LITE attributable-to-parent) stay `display_label`/`ordinal` NULL.
- **C. Liveness** — each ticker still has a sane number of display-eligible IS rows.

Run:
```bash
uv run --with supabase --with python-dateutil python3 scripts/synthetic_check_financials.py
# exit 0 = all green; exit 1 = violation (investigate before next user-facing use)
```

**Schedule** (recommended): run daily via cron / a scheduled task; alert on exit 1.
On failure, read the printed violation (it names ticker + invariant + example
row), then: confirm via the Viewer in the named statement/period, check the last
re-upsert/edit for that ticker, and either re-upsert from backup or fix forward.

## 4. Known-good baselines (for the synthetic check + manual spot-check)

- 5 tickers: AAOI / INTC / LITE / MU / SNDK, all coverage 100% display-eligible.
- SNDK IS "(Gain) loss on business divestiture" renders as **one** row in As
  Reported (dedup); the prose `Gain/Loss on business divestiture` rows are
  suppressed (value retained in DB, display nulled).
- LITE IS "Income (loss) before income taxes" is **one** row; the tag
  `IncomeLossAttributableToParent` long-tail row is suppressed.

## 5. Observability gaps (tracked, not yet built)

- No structured metrics / alerting beyond the synthetic check's exit code +
  Vercel's built-in deployment/function logs. A future step is wiring the
  synthetic check's failure to a notification channel.
- `[cfCashMovement]` emits a per-render fail-closed `warn` when a period has
  ambiguous cash-balance candidates — correct behavior, but noisy; could be
  de-duplicated/quieted (cosmetic).
