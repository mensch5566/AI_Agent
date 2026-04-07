/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useEffect } from "react";
import { getIncompleteFYs, type FinData, type ValMap } from "./constants";

/* ================================================================
   Long-format fact row from API
   ================================================================ */
export interface FactRow {
  period: string;
  period_end: string | null;
  statement: string;
  metric: string;
  dimension: string;
  value: number | null;
  unit: string | null;
  source: string | null;
}

interface CompanyInfo {
  ticker: string;
  company: string;
  cik: string;
  exchange: string;
  currency: string;
  fiscal_year_end_month: number;
  last_updated: string;
  notes: string | null;
}

export interface ApiResponse {
  ticker: string;
  company: CompanyInfo | null;
  facts: FactRow[];
}

/* ================================================================
   Pivot: long-format facts → nested FinData
   ================================================================ */

const BS_STATEMENTS: Record<string, string> = {
  balance_sheet_assets: "assets",
  balance_sheet_liabilities: "liabilities",
  balance_sheet_equity: "equity",
};
const CF_SECTIONS: Record<string, string> = {
  cash_flow_operating: "operating_activities",
  cash_flow_investing: "investing_activities",
  cash_flow_financing: "financing_activities",
};

export function pivotToFinData(api: ApiResponse): FinData {
  const { company, facts } = api;

  const isPeriods = new Set<string>();
  const bsPeriods = new Set<string>();

  const incomeStatement: Record<string, ValMap> = {};
  const balanceSheet: Record<string, Record<string, ValMap>> = {
    assets: {}, liabilities: {}, equity: {},
  };
  const cashFlow: Record<string, any> = {
    operating_activities: {},
    investing_activities: {},
    financing_activities: {},
  };
  const ratios: Record<string, Record<string, number>> = {};
  const filings: Record<string, { period_end: string }> = {};

  // Segment: metric (subsection) → period → dimension → { value, source }
  const segments: Record<string, Record<string, Record<string, { value: number; source?: string }>>> = {};
  // Non-GAAP: metric → period → { value, source }
  const nonGaap: Record<string, Record<string, { value: number; source?: string }>> = {};

  for (const row of facts) {
    const { period, period_end, statement, metric, dimension, value, source } = row;
    if (value === null) continue;

    if (period_end && !filings[period]) {
      filings[period] = { period_end };
    }

    if (statement === "income_statement") {
      isPeriods.add(period);
      if (!incomeStatement[metric]) incomeStatement[metric] = {};
      incomeStatement[metric][period] = value;
    }
    else if (statement in BS_STATEMENTS) {
      bsPeriods.add(period);
      const section = BS_STATEMENTS[statement];
      if (!balanceSheet[section][metric]) balanceSheet[section][metric] = {};
      balanceSheet[section][metric][period] = value;
    }
    else if (statement in CF_SECTIONS) {
      isPeriods.add(period);
      const section = CF_SECTIONS[statement];
      if (!cashFlow[section][metric]) cashFlow[section][metric] = {};
      cashFlow[section][metric][period] = value;
    }
    else if (statement === "cash_flow_summary") {
      isPeriods.add(period);
      if (!cashFlow[metric]) cashFlow[metric] = {};
      cashFlow[metric][period] = value;
    }
    else if (statement === "financial_ratios") {
      if (!ratios[period]) ratios[period] = {};
      ratios[period][metric] = value;
    }
    else if (statement === "segments") {
      if (!segments[metric]) segments[metric] = {};
      if (!segments[metric][period]) segments[metric][period] = {};
      segments[metric][period][dimension] = { value, source: source || undefined };
    }
    else if (statement === "non_gaap") {
      if (!nonGaap[metric]) nonGaap[metric] = {};
      nonGaap[metric][period] = { value, source: source || undefined };
    }
  }

  const sortedISPeriods = [...isPeriods].sort();
  const sortedBSPeriods = [...bsPeriods].sort();

  return {
    metadata: {
      company: company?.company,
      ticker: company?.ticker || api.ticker,
      exchange: company?.exchange,
      cik: company?.cik,
      fiscal_year_end_month: company?.fiscal_year_end_month,
      currency: company?.currency,
      unit: "millions_except_per_share",
      last_updated: company?.last_updated,
      periods_income_statement: sortedISPeriods,
      periods_balance_sheet: sortedBSPeriods,
    },
    filings,
    income_statement: incomeStatement,
    balance_sheet: balanceSheet,
    cash_flow_statement: cashFlow,
    financial_ratios: ratios,
    _segments: segments,
    _non_gaap: nonGaap,
  };
}

/* ================================================================
   Annual aggregation
   ================================================================ */

const SUM_EXCLUDE = new Set(["eps_basic", "eps_diluted", "shares_basic", "shares_diluted", "shares_basic_millions", "shares_diluted_millions"]);
const AVG_KEYS = new Set(["shares_basic", "shares_diluted", "shares_basic_millions", "shares_diluted_millions"]);

function groupByFY(periods: string[]) {
  const map: Record<string, string[]> = {};
  for (const p of periods) {
    const m = p.match(/Q(\d+)_FY(\d+)/);
    if (!m) continue;
    const fy = `FY${m[2]}`;
    if (!map[fy]) map[fy] = [];
    map[fy].push(p);
  }
  return map;
}

function aggVals(valObj: ValMap, fyMap: Record<string, string[]>, mode: "sum" | "avg" | "last") {
  const result: ValMap = {};
  for (const [fy, quarters] of Object.entries(fyMap)) {
    const vals = quarters.map((q) => valObj[q]).filter((v): v is number => v !== null && v !== undefined);
    if (!vals.length) continue;
    if (mode === "sum") result[fy] = Math.round(vals.reduce((a, b) => a + b, 0) * 100) / 100;
    else if (mode === "avg") result[fy] = Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100;
    else {
      const q4 = quarters.find((q) => q.startsWith("Q4"));
      if (q4 && valObj[q4] !== null && valObj[q4] !== undefined) result[fy] = valObj[q4];
    }
  }
  return result;
}

export function toAnnualData(data: FinData): FinData {
  const isFyMap = groupByFY(data.metadata.periods_income_statement || []);
  const bsFyMap = groupByFY(data.metadata.periods_balance_sheet || []);
  const fys = [...new Set([...Object.keys(isFyMap), ...Object.keys(bsFyMap)])].sort();

  const annIS: Record<string, ValMap> = {};
  const srcIS = data.income_statement || {};
  for (const [key, vals] of Object.entries(srcIS) as [string, ValMap][]) {
    if (SUM_EXCLUDE.has(key)) {
      if (AVG_KEYS.has(key)) annIS[key] = aggVals(vals, isFyMap, "avg");
    } else {
      annIS[key] = aggVals(vals, isFyMap, "sum");
    }
  }
  for (const epsKey of ["eps_basic", "eps_diluted"]) {
    const sharesKey = epsKey === "eps_basic" ? "shares_basic" : "shares_diluted";
    const ni = annIS.net_income || {};
    const sh = annIS[sharesKey] || annIS[sharesKey + "_millions"] || {};
    if (Object.keys(ni).length && Object.keys(sh).length) {
      annIS[epsKey] = {};
      for (const fy of fys) {
        if (ni[fy] !== undefined && ni[fy] !== null && sh[fy] && sh[fy] !== 0)
          annIS[epsKey][fy] = Math.round((ni[fy]! / sh[fy]!) * 100) / 100;
      }
    }
  }

  const annBS: Record<string, Record<string, ValMap>> = { assets: {}, liabilities: {}, equity: {} };
  const srcBS = data.balance_sheet || {};
  for (const sec of ["assets", "liabilities", "equity"] as const) {
    if (!srcBS[sec]) continue;
    for (const [key, vals] of Object.entries(srcBS[sec]) as [string, ValMap][]) {
      annBS[sec][key] = aggVals(vals, bsFyMap, "last");
    }
  }

  const annCF: any = {};
  const srcCF = data.cash_flow_statement || {};
  for (const secKey of ["operating_activities", "investing_activities", "financing_activities"]) {
    if (!srcCF[secKey]) continue;
    annCF[secKey] = {};
    for (const [key, vals] of Object.entries(srcCF[secKey])) {
      if (typeof vals === "object" && vals !== null && !Array.isArray(vals))
        annCF[secKey][key] = aggVals(vals as ValMap, isFyMap, "sum");
    }
  }
  for (const key of ["fx_effect_on_cash", "net_change_in_cash", "free_cash_flow"]) {
    if (srcCF[key] && typeof srcCF[key] === "object") annCF[key] = aggVals(srcCF[key], isFyMap, "sum");
  }
  if (srcCF.ending_cash) annCF.ending_cash = aggVals(srcCF.ending_cash, isFyMap, "last");
  if (srcCF.beginning_cash) {
    const bc: ValMap = {};
    for (const [fy, quarters] of Object.entries(isFyMap)) {
      const q1 = quarters.find((q) => q.startsWith("Q1"));
      if (q1 && srcCF.beginning_cash[q1] !== undefined) bc[fy] = srcCF.beginning_cash[q1];
    }
    annCF.beginning_cash = bc;
  }

  const annRatios: Record<string, Record<string, number>> = {};
  for (const fy of fys) {
    const r: Record<string, number> = {};
    const g = (sec: string, key: string) => annBS[sec]?.[key]?.[fy];
    const ca = g("assets", "total_current_assets");
    const cl = g("liabilities", "total_current_liabilities");
    const inv = g("assets", "inventories");
    const cash = g("assets", "cash_and_cash_equivalents");
    const ta = g("assets", "total_assets");
    const tl = g("liabilities", "total_liabilities");
    const te = g("equity", "total_equity");
    const ltd = g("liabilities", "long_term_debt") || 0;
    const cd = g("liabilities", "current_debt") || 0;
    const totalDebt = ltd + cd;
    const rev = annIS.revenue?.[fy];
    const gp = annIS.gross_profit?.[fy];
    const oi = annIS.operating_income?.[fy];
    const ni = annIS.net_income?.[fy];
    const intExp = annIS.interest_expense?.[fy];
    const ocf = annCF.operating_activities?.net_cash_from_operating?.[fy];
    const capex = annCF.investing_activities?.capital_expenditures?.[fy];
    const fcfVal = ocf != null && capex != null ? ocf - capex : annCF.free_cash_flow?.[fy];

    const rnd = (v: number) => Math.round(v * 100) / 100;
    const rnd4 = (v: number) => Math.round(v * 10000) / 10000;
    if (ca && cl && cl !== 0) r.current_ratio = rnd(ca / cl);
    if (ca != null && cl && cl !== 0) r.quick_ratio = rnd((ca - (inv || 0)) / cl);
    if (tl != null && te && te !== 0) r.debt_to_equity = rnd(tl / te);
    if (totalDebt && te && te !== 0) r.net_debt_to_equity = rnd((totalDebt - (cash || 0)) / te);
    if (ta && ta !== 0 && te != null) r.equity_ratio = rnd4(te / ta);
    if (gp != null && rev && rev !== 0) r.gross_margin_pct = rnd4(gp / rev);
    if (oi != null && rev && rev !== 0) r.operating_margin_pct = rnd4(oi / rev);
    if (ni != null && rev && rev !== 0) r.net_margin_pct = rnd4(ni / rev);
    if (ni != null && te && te !== 0) r.roe = rnd4(ni / te);
    if (ni != null && ta && ta !== 0) r.roa = rnd4(ni / ta);
    if (rev != null && ta && ta !== 0) r.asset_turnover = rnd4(rev / ta);
    if (oi != null && intExp && intExp !== 0) r.interest_coverage = rnd(oi / intExp);
    if (fcfVal != null && rev && rev !== 0) r.fcf_margin_pct = rnd4(fcfVal / rev);

    if (Object.keys(r).length) annRatios[fy] = r;
  }

  const annFilings: any = {};
  for (const [fy, quarters] of Object.entries(bsFyMap)) {
    const q4 = quarters.find((q) => q.startsWith("Q4"));
    if (q4 && data.filings?.[q4]) annFilings[fy] = data.filings[q4];
  }

  const allQuarterly = [...(data.metadata.periods_income_statement || []), ...(data.metadata.periods_balance_sheet || [])];
  const incompleteFYs = Object.fromEntries(getIncompleteFYs(allQuarterly));

  return {
    metadata: { ...data.metadata, periods_income_statement: fys, periods_balance_sheet: fys, incomplete_fys: incompleteFYs },
    filings: annFilings,
    income_statement: annIS,
    balance_sheet: annBS,
    cash_flow_statement: annCF,
    financial_ratios: annRatios,
    _segments: data._segments,
    _non_gaap: data._non_gaap,
  };
}

/* ================================================================
   Data fetching hook with module-level cache
   ================================================================ */

const cache = new Map<string, FinData>();

export function useFinancialData(ticker: string) {
  const [data, setData] = useState<FinData | null>(cache.get(ticker) ?? null);
  const [loading, setLoading] = useState(!cache.has(ticker));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) {
      setData(null);
      setLoading(false);
      return;
    }
    if (cache.has(ticker)) {
      setData(cache.get(ticker)!);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`/api/financials/${ticker}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<ApiResponse>;
      })
      .then((apiData) => {
        if (cancelled) return;
        const finData = pivotToFinData(apiData);
        cache.set(ticker, finData);
        setData(finData);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e.message);
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [ticker]);

  return { data, loading, error };
}
