/* eslint-disable @typescript-eslint/no-explicit-any */

import { sortPeriods } from "./constants";

/* ================================================================
   Types
   ================================================================ */
export interface FactRow {
  period: string;
  period_end: string | null;
  statement: string;
  metric: string;
  dimension: string;
  value: number;
  unit: string | null;
  source: string | null;
}

export interface CompanyInfo {
  ticker: string;
  company: string;
  cik: string;
  exchange: string;
  currency: string;
  fiscal_year_end_month: number;
  last_updated: string;
  notes: string | null;
}

export type ValMap = Record<string, number | null>;

/* ================================================================
   FactStore — indexed wrapper around flat fact rows
   ================================================================ */
export class FactStore {
  readonly facts: FactRow[];
  readonly company: CompanyInfo | null;

  // Indexes: statement → metric → dimension → period → value
  private idx: Map<string, Map<string, Map<string, Map<string, number>>>> = new Map();
  // period_end cache: period → period_end
  private periodEnds: Map<string, string> = new Map();
  // source cache: statement → metric → dimension → period → source
  private sourceIdx: Map<string, Map<string, Map<string, Map<string, string>>>> = new Map();

  constructor(facts: FactRow[], company: CompanyInfo | null) {
    this.facts = facts;
    this.company = company;
    this._buildIndex();
  }

  private _buildIndex() {
    for (const f of this.facts) {
      if (f.value === null) continue;

      // Main value index
      let stmtMap = this.idx.get(f.statement);
      if (!stmtMap) { stmtMap = new Map(); this.idx.set(f.statement, stmtMap); }
      let metricMap = stmtMap.get(f.metric);
      if (!metricMap) { metricMap = new Map(); stmtMap.set(f.metric, metricMap); }
      let dimMap = metricMap.get(f.dimension);
      if (!dimMap) { dimMap = new Map(); metricMap.set(f.dimension, dimMap); }
      dimMap.set(f.period, f.value);

      // period_end
      if (f.period_end) this.periodEnds.set(f.period, f.period_end);

      // source index
      if (f.source) {
        let sStmt = this.sourceIdx.get(f.statement);
        if (!sStmt) { sStmt = new Map(); this.sourceIdx.set(f.statement, sStmt); }
        let sMetric = sStmt.get(f.metric);
        if (!sMetric) { sMetric = new Map(); sStmt.set(f.metric, sMetric); }
        let sDim = sMetric.get(f.dimension);
        if (!sDim) { sDim = new Map(); sMetric.set(f.dimension, sDim); }
        sDim.set(f.period, f.source);
      }
    }
  }

  /* ── Lookups ─────────────────────────────────────────────────── */

  /** Get single value */
  val(statement: string, metric: string, period: string, dimension = ""): number | null {
    return this.idx.get(statement)?.get(metric)?.get(dimension)?.get(period) ?? null;
  }

  /** Get ValMap (period → value) for a metric */
  valMap(statement: string, metric: string, dimension = ""): ValMap {
    const dimMap = this.idx.get(statement)?.get(metric)?.get(dimension);
    if (!dimMap) return {};
    return Object.fromEntries(dimMap);
  }

  /** Get source string */
  source(statement: string, metric: string, period: string, dimension = ""): string | null {
    return this.sourceIdx.get(statement)?.get(metric)?.get(dimension)?.get(period) ?? null;
  }

  /** Get period_end for a period */
  periodEnd(period: string): string {
    return this.periodEnds.get(period) ?? "";
  }

  /* ── Period queries ──────────────────────────────────────────── */

  /** Get sorted unique periods for given statements */
  periods(...statements: string[]): string[] {
    const set = new Set<string>();
    for (const stmt of statements) {
      const stmtMap = this.idx.get(stmt);
      if (!stmtMap) continue;
      for (const metricMap of stmtMap.values()) {
        for (const dimMap of metricMap.values()) {
          for (const p of dimMap.keys()) set.add(p);
        }
      }
    }
    return sortPeriods([...set]);
  }

  /** Get sorted unique periods across IS + CF statements */
  periodsIS(): string[] {
    return this.periods(
      "income_statement",
      "cash_flow_operating", "cash_flow_investing", "cash_flow_financing", "cash_flow_summary",
    );
  }

  /** Get sorted unique periods for balance sheet */
  periodsBS(): string[] {
    return this.periods("balance_sheet_assets", "balance_sheet_liabilities", "balance_sheet_equity");
  }

  /* ── Metric queries ─────────────────────────────────────────── */

  /** Get all metric names for a statement (in insertion order) */
  metrics(statement: string): string[] {
    return [...(this.idx.get(statement)?.keys() ?? [])];
  }

  /** Get all dimension names for a statement + metric */
  dimensions(statement: string, metric: string): string[] {
    const metricMap = this.idx.get(statement)?.get(metric);
    if (!metricMap) return [];
    return [...metricMap.keys()].filter(d => d !== "");
  }

  /* ── Segment helpers ─────────────────────────────────────────── */

  /** Get segment categories (e.g. revenue_by_product, revenue_by_geography) */
  segmentCategories(): string[] {
    return this.metrics("segments");
  }

  /** Get segment data for a category: { dimension → period → value } */
  segmentData(category: string): Record<string, ValMap> {
    const metricMap = this.idx.get("segments")?.get(category);
    if (!metricMap) return {};
    const result: Record<string, ValMap> = {};
    for (const [dim, periodMap] of metricMap) {
      if (!dim) continue;
      result[dim] = Object.fromEntries(periodMap);
    }
    return result;
  }

  /** Get segment source for a specific cell */
  segmentSource(category: string, dimension: string, period: string): string | null {
    return this.source("segments", category, period, dimension);
  }

  /** Get unique periods for segments */
  segmentPeriods(category: string): string[] {
    const metricMap = this.idx.get("segments")?.get(category);
    if (!metricMap) return [];
    const set = new Set<string>();
    for (const dimMap of metricMap.values()) {
      for (const p of dimMap.keys()) set.add(p);
    }
    return sortPeriods([...set]);
  }

  /* ── Non-GAAP helpers ────────────────────────────────────────── */

  /** Get non-GAAP metric names */
  nonGaapMetrics(): string[] {
    return this.metrics("non_gaap");
  }

  /** Get non-GAAP ValMap for a metric */
  nonGaapValMap(metric: string): ValMap {
    return this.valMap("non_gaap", metric);
  }

  /** Get non-GAAP source */
  nonGaapSource(metric: string, period: string): string | null {
    return this.source("non_gaap", metric, period);
  }

  /* ── Annual aggregation ─────────────────────────────────────── */

  /** Create a new FactStore with quarterly data aggregated to annual */
  toAnnual(): FactStore {
    const SUM_EXCLUDE = new Set([
      "eps_basic", "eps_diluted",
      "shares_basic", "shares_diluted", "shares_basic_millions", "shares_diluted_millions",
      // pct metrics must NOT be summed — they'll be recomputed from annual totals
      "gross_margin_pct", "operating_margin_pct", "net_margin_pct",
      "effective_tax_rate",
    ]);
    const AVG_KEYS = new Set(["shares_basic", "shares_diluted", "shares_basic_millions", "shares_diluted_millions"]);
    const LAST_STATEMENTS = new Set(["balance_sheet_assets", "balance_sheet_liabilities", "balance_sheet_equity"]);

    // Group periods by FY
    const fyMap: Record<string, string[]> = {};
    const allPeriods = new Set<string>();
    for (const f of this.facts) allPeriods.add(f.period);
    for (const p of allPeriods) {
      const m = p.match(/^Q(\d+)_FY(\d+)$/);
      if (!m) continue;
      const fy = `FY${m[2]}`;
      if (!fyMap[fy]) fyMap[fy] = [];
      fyMap[fy].push(p);
    }

    const annualFacts: FactRow[] = [];

    for (const [stmt, metricMap] of this.idx) {
      if (stmt === "financial_ratios") continue; // ratios will be recomputed

      for (const [metric, dimMapOuter] of metricMap) {
        for (const [dim, periodMap] of dimMapOuter) {
          const isBS = LAST_STATEMENTS.has(stmt);
          const isAvg = AVG_KEYS.has(metric);
          const isSkipSum = SUM_EXCLUDE.has(metric);

          for (const [fy, quarters] of Object.entries(fyMap)) {
            const vals = quarters.map(q => periodMap.get(q)).filter((v): v is number => v != null);
            if (!vals.length) continue;

            let value: number;
            if (isBS) {
              // Balance sheet: take Q4 (last)
              const q4 = quarters.find(q => q.startsWith("Q4"));
              const q4Val = q4 ? periodMap.get(q4) : undefined;
              if (q4Val == null) continue;
              value = q4Val;
            } else if (isSkipSum && !isAvg) {
              continue; // skip EPS (will be recomputed)
            } else if (isAvg) {
              value = Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100;
            } else {
              value = Math.round(vals.reduce((a, b) => a + b, 0) * 100) / 100;
            }

            annualFacts.push({
              period: fy,
              period_end: null,
              statement: stmt,
              metric,
              dimension: dim,
              value,
              unit: null,
              source: null,
            });
          }
        }
      }
    }

    // Recompute annual EPS = net_income / shares
    for (const epsKey of ["eps_basic", "eps_diluted"]) {
      const sharesKey = epsKey === "eps_basic" ? "shares_basic" : "shares_diluted";
      for (const fy of Object.keys(fyMap)) {
        const ni = annualFacts.find(f => f.statement === "income_statement" && f.metric === "net_income" && f.period === fy);
        const sh = annualFacts.find(f => f.statement === "income_statement" && f.metric === sharesKey && f.period === fy)
          || annualFacts.find(f => f.statement === "income_statement" && f.metric === sharesKey + "_millions" && f.period === fy);
        if (ni && sh && sh.value !== 0) {
          annualFacts.push({
            period: fy,
            period_end: null,
            statement: "income_statement",
            metric: epsKey,
            dimension: "",
            value: Math.round((ni.value / sh.value) * 100) / 100,
            unit: null,
            source: null,
          });
        }
      }
    }

    // Recompute annual ratios
    for (const fy of Object.keys(fyMap)) {
      const v = (stmt: string, metric: string) =>
        annualFacts.find(f => f.statement === stmt && f.metric === metric && f.period === fy)?.value ?? null;

      const ca = v("balance_sheet_assets", "total_current_assets");
      const cl = v("balance_sheet_liabilities", "total_current_liabilities");
      const inv = v("balance_sheet_assets", "inventories");
      const cash = v("balance_sheet_assets", "cash_and_cash_equivalents");
      const ta = v("balance_sheet_assets", "total_assets");
      const tl = v("balance_sheet_liabilities", "total_liabilities");
      const te = v("balance_sheet_equity", "total_equity");
      const ltd = v("balance_sheet_liabilities", "long_term_debt") ?? 0;
      const cd = v("balance_sheet_liabilities", "current_debt") ?? 0;
      const totalDebt = ltd + cd;
      const rev = v("income_statement", "revenue");
      const gp = v("income_statement", "gross_profit");
      const oi = v("income_statement", "operating_income");
      const ni = v("income_statement", "net_income");
      const intExp = v("income_statement", "interest_expense");
      const ocf = v("cash_flow_operating", "net_cash_from_operating");
      const capex = v("cash_flow_investing", "capital_expenditures");
      const fcf = ocf != null && capex != null ? ocf - capex
        : v("cash_flow_summary", "free_cash_flow");

      const rnd = (n: number) => Math.round(n * 100) / 100;
      const rnd4 = (n: number) => Math.round(n * 10000) / 10000;
      const ratios: [string, number][] = [];

      if (ca && cl && cl !== 0) ratios.push(["current_ratio", rnd(ca / cl)]);
      if (ca != null && cl && cl !== 0) ratios.push(["quick_ratio", rnd((ca - (inv ?? 0)) / cl)]);
      if (tl != null && te && te !== 0) ratios.push(["debt_to_equity", rnd(tl / te)]);
      if (totalDebt && te && te !== 0) ratios.push(["net_debt_to_equity", rnd((totalDebt - (cash ?? 0)) / te)]);
      if (ta && ta !== 0 && te != null) ratios.push(["equity_ratio", rnd4(te / ta)]);
      if (gp != null && rev && rev !== 0) ratios.push(["gross_margin_pct", rnd4(gp / rev)]);
      if (oi != null && rev && rev !== 0) ratios.push(["operating_margin_pct", rnd4(oi / rev)]);
      if (ni != null && rev && rev !== 0) ratios.push(["net_margin_pct", rnd4(ni / rev)]);
      if (ni != null && te && te !== 0) ratios.push(["roe", rnd4(ni / te)]);
      if (ni != null && ta && ta !== 0) ratios.push(["roa", rnd4(ni / ta)]);
      if (rev != null && ta && ta !== 0) ratios.push(["asset_turnover", rnd4(rev / ta)]);
      if (oi != null && intExp && intExp !== 0) ratios.push(["interest_coverage", rnd(oi / intExp)]);
      if (fcf != null && rev && rev !== 0) ratios.push(["fcf_margin_pct", rnd4(fcf / rev)]);

      for (const [metric, value] of ratios) {
        annualFacts.push({
          period: fy,
          period_end: null,
          statement: "financial_ratios",
          metric,
          dimension: "",
          value,
          unit: null,
          source: null,
        });
      }

      // Also write IS-level pct metrics back to income_statement so IS table shows correct annual values
      const isTaxExp = v("income_statement", "income_tax_expense");
      const isIbt = v("income_statement", "income_before_taxes");
      const isPctFacts: [string, number | null][] = [
        ["gross_margin_pct", gp != null && rev ? rnd4(gp / rev) : null],
        ["operating_margin_pct", oi != null && rev ? rnd4(oi / rev) : null],
        ["net_margin_pct", ni != null && rev ? rnd4(ni / rev) : null],
        ["effective_tax_rate", isTaxExp != null && isIbt && isIbt !== 0 ? rnd4(isTaxExp / isIbt) : null],
      ];
      for (const [metric, value] of isPctFacts) {
        if (value == null) continue;
        annualFacts.push({
          period: fy,
          period_end: null,
          statement: "income_statement",
          metric,
          dimension: "",
          value,
          unit: null,
          source: null,
        });
      }
    }

    // Mark incomplete FYs (< 4 quarters) via _meta facts
    for (const [fy, quarters] of Object.entries(fyMap)) {
      if (quarters.length < 4) {
        annualFacts.push({
          period: fy,
          period_end: null,
          statement: "_meta",
          metric: "incomplete_fy_quarters",
          dimension: "",
          value: quarters.length,
          unit: null,
          source: null,
        });
      }
    }

    return new FactStore(annualFacts, this.company);
  }

  /** Get incomplete FY quarter count (only meaningful in annual store) */
  incompleteFYQuarters(fy: string): number | null {
    return this.val("_meta", "incomplete_fy_quarters", fy);
  }

  /* ── Convenience ─────────────────────────────────────────────── */

  get currency(): string {
    return this.company?.currency ?? "USD";
  }

  get ticker(): string {
    return this.company?.ticker ?? "";
  }
}
