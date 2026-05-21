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

function displayValue(c: Cell | undefined, signFlipConcepts: Set<string>): string {
  if (!c) return "—";
  const flip = !!c.xbrl_tag && signFlipConcepts.has(c.xbrl_tag);
  const v = flip ? -Math.abs(c.value) : c.value;
  if (v < 0) return `(${fmtValue(Math.abs(v), c.unit, c.uni_account)})`;
  return fmtValue(v, c.unit, c.uni_account);
}

function statusTooltip(status: CellStatus, c?: Cell): string {
  if (!c) return "pending — not derived yet";
  // Aggregated long-tail bucket — list children with their values.
  const prov = c.provenance as Record<string, unknown> | null;
  if (prov && prov.aggregation === "long_tail_sum") {
    const children = (prov.children as Array<Record<string, unknown>>) ?? [];
    const lines = children.map((ch) => {
      const sign = (ch.weight as number) === -1 ? "-" : "+";
      const rolls = ch.rolls_up_to ? ` → ${ch.rolls_up_to}` : "";
      return `${sign} ${ch.source_account}: ${ch.value}${rolls}`;
    });
    return `long-tail bucket (${children.length} child${children.length === 1 ? "" : "ren"}):\n${lines.join("\n")}`;
  }
  if (status === "DERIVED_FROM_DISCLOSED") {
    const f = prov?.formula;
    return f ? `derived: ${f}` : "derived";
  }
  if (status === "EXCLUDED_FROM_NONGAAP") return "excluded by Non-GAAP definition";
  if (status === "SOURCE_OF_TRUTH") {
    const f = prov?.source_filing;
    const a = prov?.accession_number;
    return `source: ${f ?? "filing"}${a ? ` (${a})` : ""}`;
  }
  return "";
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
                  const cells = [
                    <td
                      key={`${row.key}-${p}-g`}
                      className={`text-right px-3 py-1.5 whitespace-nowrap ${pres.className}`}
                      title={statusTooltip(m?.status ?? "PENDING", c)}
                    >
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
