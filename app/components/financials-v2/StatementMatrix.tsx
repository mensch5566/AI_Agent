"use client";

import type { Cell, CellStatus } from "./types";
import type { Matrix } from "./useFinancialMatrix";
import { CHART_COLORS, NONGAAP_SPOTLIGHT_METRICS, comparePeriods, fmtValue } from "./constants";

type Props = {
  gaap: Matrix;
  nongaap?: Matrix;
  showNongaapColumn?: boolean;
  signFlipConcepts?: string[];
  /** Ordered list of uni_account keys currently plotted in the chart above. */
  selectedKeys?: string[];
  /** Click handler — fires when the user clicks a row to toggle its chart selection. */
  onToggleRow?: (key: string) => void;
  /** Keys of rows with at least one populated cell. Rows not in this set
   *  render as non-clickable (no chart data to plot). */
  rowsWithData?: Set<string>;
};

function statusPresentation(status: CellStatus): { className: string } {
  switch (status) {
    case "SOURCE_OF_TRUTH":
      return { className: "text-foreground" };
    case "DERIVED_FROM_DISCLOSED":
      return { className: "italic text-muted-foreground" };
    case "EXCLUDED_FROM_NONGAAP":
      return { className: "line-through text-muted-foreground/60" };
    default:
      return { className: "italic text-muted-foreground/60" };
  }
}

// Effective tax rate = income_tax_expense / income_before_taxes. When pre-tax
// income is <= 0 (loss period) the quotient is mathematically defined but
// financially meaningless — a tiny tax expense over a large loss reads as
// "0.0%" and a tax benefit reads as a misleading negative rate. Detect this
// from the derived cell's own provenance.inputs and render "N/M" instead.
// Directly-disclosed (Non-GAAP) tax rates carry no inputs; we trust the value
// management reported and never override those.
function etrNotMeaningful(c: Cell): boolean {
  if (c.uni_account !== "effective_tax_rate") return false;
  const prov = c.provenance as Record<string, unknown> | null;
  const inputs = prov?.inputs as Array<{ uni_account?: string; value?: number }> | undefined;
  if (!inputs) return false;
  const ibt = inputs.find((i) => i.uni_account === "income_before_taxes");
  return !!ibt && typeof ibt.value === "number" && ibt.value <= 0;
}

function displayValue(c: Cell | undefined, signFlipConcepts: Set<string>): string {
  if (!c) return "—";
  if (etrNotMeaningful(c)) return "N/M";
  const flip = !!c.xbrl_tag && signFlipConcepts.has(c.xbrl_tag);
  const v = flip ? -Math.abs(c.value) : c.value;
  if (v < 0) return `(${fmtValue(Math.abs(v), c.unit, c.uni_account)})`;
  return fmtValue(v, c.unit, c.uni_account);
}

// Phase 6.2: schema v4 manual audit / classification badge + tooltip suffix.
// Cells whose provenance carries `audit_source` (canonical or legacy raw)
// display a "✓" badge; derived cells with `has_audited_inputs=true` get the
// same indicator since their value traces back to audited inputs.
// `classification_source` (without audit) gets a separate "·" marker.
const MANUAL_AUDIT_SOURCES = new Set([
  "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
  "MANUAL_RESTATEMENT_FROM_AMENDED_FILING",
  // Legacy enums still recognized while DB migration is pending (Phase 6.3)
  "MANUAL_AUDIT_FROM_PDF",
  "MANUAL_AUDIT_FROM_8K_PDF",
]);

function isAuditedProvenance(prov: Record<string, unknown> | null | undefined): boolean {
  if (!prov) return false;
  const src = prov.audit_source as string | undefined;
  const rawSrc = prov.audit_source_raw as string | undefined;
  if (src && MANUAL_AUDIT_SOURCES.has(src)) return true;
  if (rawSrc && MANUAL_AUDIT_SOURCES.has(rawSrc)) return true;
  // Derived row schema §8.2
  if (prov.has_audited_inputs === true) return true;
  return false;
}

function isClassifiedProvenance(prov: Record<string, unknown> | null | undefined): boolean {
  if (!prov) return false;
  const cs = prov.classification_source as string | undefined;
  return cs === "AGENT_CLASSIFIED" || cs === "MANUAL_RECLASSIFIED";
}

function auditBadge(c?: Cell): string {
  if (!c) return "";
  const prov = c.provenance as Record<string, unknown> | null;
  if (isAuditedProvenance(prov)) return "✓";
  if (isClassifiedProvenance(prov)) return "·";
  return "";
}

function auditTooltipSuffix(c?: Cell): string {
  if (!c) return "";
  const prov = c.provenance as Record<string, unknown> | null;
  if (!prov) return "";
  const parts: string[] = [];
  if (isAuditedProvenance(prov)) {
    const src = (prov.audit_source as string | undefined) ?? (prov.audit_source_raw as string | undefined);
    if (src) parts.push(`audit: ${src}`);
    const note = prov.audit_note as string | undefined;
    if (note) parts.push(`note: ${note}`);
    const by = prov.audited_by as string | undefined;
    if (by) parts.push(`by: ${by}`);
    const at = prov.audited_at as string | undefined;
    if (at) parts.push(`at: ${at}`);
    const ev = prov.audit_evidence as Record<string, unknown> | undefined;
    if (ev) {
      const doc = ev.source_doc as string | undefined;
      const sec = ev.page_or_section as string | undefined;
      if (doc) parts.push(`source: ${doc}`);
      if (sec) parts.push(`section: ${sec}`);
    }
    // Derived row lineage
    if (prov.has_audited_inputs === true) {
      const ids = prov.audited_input_cell_ids as string[] | undefined;
      if (ids && ids.length) parts.push(`derived from ${ids.length} audited input(s)`);
    }
  } else if (isClassifiedProvenance(prov)) {
    const cs = prov.classification_source as string;
    parts.push(`classification: ${cs}`);
    const cn = prov.classification_note as string | undefined;
    if (cn) parts.push(`note: ${cn}`);
  }
  // Preservation event (Phase 4 / 5): show only when set
  const evt = prov.preservation_event as string | undefined;
  if (evt) parts.push(`preserved: ${evt}`);
  if (prov.new_extract_value_rejected !== undefined) {
    parts.push(`rejected new extract: ${prov.new_extract_value_rejected}`);
  }
  return parts.length ? "\n" + parts.join("\n") : "";
}

function statusTooltip(status: CellStatus, c?: Cell): string {
  if (!c) return "pending — not derived yet";
  // Aggregated long-tail bucket — list children with their values.
  const prov = c.provenance as Record<string, unknown> | null;
  let base = "";
  if (prov && prov.aggregation === "long_tail_sum") {
    const children = (prov.children as Array<Record<string, unknown>>) ?? [];
    const lines = children.map((ch) => {
      const sign = (ch.weight as number) === -1 ? "-" : "+";
      const rolls = ch.rolls_up_to ? ` → ${ch.rolls_up_to}` : "";
      return `${sign} ${ch.source_account}: ${ch.value}${rolls}`;
    });
    base = `long-tail bucket (${children.length} child${children.length === 1 ? "" : "ren"}):\n${lines.join("\n")}`;
  } else if (status === "DERIVED_FROM_DISCLOSED") {
    const f = prov?.formula;
    base = f ? `derived: ${f}` : "derived";
  } else if (status === "EXCLUDED_FROM_NONGAAP") {
    base = "excluded by Non-GAAP definition";
  } else if (status === "SOURCE_OF_TRUTH") {
    const f = prov?.source_filing;
    const a = prov?.accession_number;
    base = `source: ${f ?? "filing"}${a ? ` (${a})` : ""}`;
  }
  const etrNote = etrNotMeaningful(c)
    ? "\nN/M — effective tax rate not meaningful (pre-tax income ≤ 0)"
    : "";
  return base + etrNote + auditTooltipSuffix(c);
}

export function StatementMatrix({
  gaap,
  nongaap,
  showNongaapColumn = false,
  signFlipConcepts = [],
  selectedKeys = [],
  onToggleRow,
  rowsWithData,
}: Props) {
  const flipSet = new Set(signFlipConcepts);
  // Selection order → color index (matches MatrixChart's CHART_COLORS cycle).
  const selectionIndex = new Map<string, number>();
  selectedKeys.forEach((k, i) => selectionIndex.set(k, i));
  // Union of GAAP and Non-GAAP periods — Non-GAAP 8-K data may carry quarters
  // (e.g. Q4) that the GAAP feed hasn't derived yet, and we still want those
  // columns visible. GAAP-only cells show "—" in the Non-GAAP slot and vice
  // versa.
  const periods = (() => {
    if (!nongaap || !showNongaapColumn) return gaap.periods;
    const set = new Set<string>(gaap.periods);
    for (const p of nongaap.periods) set.add(p);
    return Array.from(set).sort(comparePeriods);
  })();

  if (periods.length === 0) {
    return <div className="p-4 text-sm text-muted-foreground">No data available for this view.</div>;
  }

  return (
    <div className="overflow-x-auto rounded border border-border bg-card">
      <table className="text-sm border-collapse w-full">
        <thead>
          <tr className="border-b border-border bg-muted">
            <th
              className="text-left px-3 py-2 sticky left-0 z-10 font-semibold text-foreground"
              style={{ background: "var(--muted)" }}
            >
              Metric
            </th>
            {periods.map((p) => (
              <th
                key={p}
                colSpan={showNongaapColumn ? 2 : 1}
                className="text-right px-3 py-2 whitespace-nowrap font-semibold text-foreground"
              >
                {p}
              </th>
            ))}
          </tr>
          {showNongaapColumn && (
            <tr className="border-b border-border text-xs text-muted-foreground">
              <th
                className="text-left px-3 py-1 sticky left-0 z-10"
                style={{ background: "var(--muted)" }}
              ></th>
              {periods.flatMap((p) => [
                <th key={`${p}-g`} className="text-right px-3 py-1">
                  GAAP
                </th>,
                <th key={`${p}-n`} className="text-right px-3 py-1">
                  Non-GAAP
                </th>,
              ])}
            </tr>
          )}
        </thead>
        <tbody>
          {gaap.rows.map((row) => {
            const isSubtotal = row.kind === "subtotal";
            const isLongTail = row.kind === "long_tail_bucket";
            const isDerivedRow = row.kind === "derived_ratio";
            const showNgForThisRow =
              showNongaapColumn && NONGAAP_SPOTLIGHT_METRICS.has(row.key);
            const indentPx = (row.indent ?? 0) * 12;
            const rowBg = isSubtotal ? "var(--muted)" : "var(--card)";
            const selIdx = selectionIndex.get(row.key);
            const isSelected = selIdx !== undefined;
            const selColor = isSelected ? CHART_COLORS[selIdx % CHART_COLORS.length] : null;
            const hasData = rowsWithData ? rowsWithData.has(row.key) : true;
            const clickable = !!onToggleRow && hasData;
            return (
              <tr
                key={row.key}
                className={
                  "border-b border-border " +
                  (isSubtotal ? "font-semibold " : "") +
                  (isDerivedRow ? "italic " : "") +
                  (clickable ? "cursor-pointer hover:bg-accent/40 " : "") +
                  (isSelected ? "bg-accent/30 " : "")
                }
                style={{
                  background: isSelected ? undefined : rowBg,
                }}
                onClick={clickable ? () => onToggleRow!(row.key) : undefined}
                title={
                  clickable
                    ? isSelected
                      ? `Click to remove "${row.label}" from chart`
                      : `Click to plot "${row.label}"`
                    : hasData
                      ? undefined
                      : "no data to plot"
                }
              >
                <td
                  className={
                    "px-3 py-1.5 sticky left-0 z-10 " +
                    (isLongTail ? "italic text-muted-foreground" : "text-foreground")
                  }
                  style={{
                    paddingLeft: 12 + indentPx,
                    // Always opaque so the sticky Metric column hides scrolled-away
                    // numbers underneath. The selection indicator is rendered as an
                    // inset left bar here (moved from <tr>) so the opaque td doesn't
                    // mask it.
                    background: rowBg,
                    boxShadow: selColor ? `inset 3px 0 0 ${selColor}` : undefined,
                  }}
                >
                  {selColor && (
                    <span
                      className="inline-block w-2 h-2 rounded-full align-middle mr-1.5"
                      style={{ background: selColor }}
                    />
                  )}
                  {row.label}
                </td>
                {periods.flatMap((p) => {
                  const m = gaap.cells[row.key]?.[p];
                  const c = m?.cell;
                  const ngCellWrap = showNgForThisRow ? nongaap?.cells[row.key]?.[p] : undefined;
                  const ng = ngCellWrap?.cell;
                  const pres = statusPresentation(m?.status ?? "PENDING");
                  const gBadge = auditBadge(c);
                  const cells = [
                    <td
                      key={`${row.key}-${p}-g`}
                      className={`text-right px-3 py-1.5 whitespace-nowrap ${pres.className}`}
                      title={statusTooltip(m?.status ?? "PENDING", c)}
                    >
                      {gBadge && (
                        <span
                          className="text-emerald-600 dark:text-emerald-400 mr-1 select-none"
                          aria-label="manually audited"
                        >
                          {gBadge}
                        </span>
                      )}
                      {displayValue(c, flipSet)}
                    </td>,
                  ];
                  // Whenever the table-wide Non-GAAP column is on, we MUST
                  // render a second <td> per period so cells align with the
                  // colSpan=2 header. Rows not in NONGAAP_SPOTLIGHT_METRICS
                  // get a placeholder dash instead of a real Non-GAAP value.
                  if (showNongaapColumn) {
                    if (showNgForThisRow) {
                      const npres = statusPresentation(ngCellWrap?.status ?? "PENDING");
                      const nBadge = auditBadge(ng);
                      cells.push(
                        <td
                          key={`${row.key}-${p}-n`}
                          className={`text-right px-3 py-1.5 whitespace-nowrap ${npres.className}`}
                          title={
                            ng
                              ? statusTooltip(ngCellWrap?.status ?? "PENDING", ng)
                              : "not disclosed by management"
                          }
                        >
                          {nBadge && (
                            <span
                              className="text-emerald-600 dark:text-emerald-400 mr-1 select-none"
                              aria-label="manually audited"
                            >
                              {nBadge}
                            </span>
                          )}
                          {displayValue(ng, flipSet)}
                        </td>,
                      );
                    } else {
                      cells.push(
                        <td
                          key={`${row.key}-${p}-n`}
                          className="text-right px-3 py-1.5 whitespace-nowrap text-muted-foreground/40"
                          title="no Non-GAAP spotlight for this metric"
                        >
                          —
                        </td>,
                      );
                    }
                  }
                  return cells;
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
