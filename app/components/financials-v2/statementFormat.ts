// Statement-scoped (IS / BS / CF) number formatter — PDF-faithful.
//
// Used ONLY by the three financial statements, never by the Ratios view. PDF
// statements report whole-dollar amounts with thousands separators (the cell's
// `unit` already encodes the millions/thousands scale, so we format the stored
// number as-is, not rescale it), EPS to 2 decimals, and negatives in
// parentheses. The Ratios view keeps its own formatter (`fmtValue`) so
// percentages / multiples / days are unaffected.
//
// Returns `null` for units this formatter does not own (e.g. `Pure` ratios,
// share counts) so the caller can fall back to the existing `fmtValue` for any
// non-money/non-EPS cell that happens to appear in a statement.

const MONEY_UNITS = new Set(["USD_millions", "USD_thousands"]);

function parenIfNegative(formatted: string, negative: boolean): string {
  return negative ? `(${formatted})` : formatted;
}

/**
 * Format a statement cell value for the IS/BS/CF table.
 * - money (`USD_millions` / `USD_thousands`): whole number, thousands
 *   separators, no decimals; negatives in parentheses.
 * - EPS (`USD_per_share`): 2 decimals; negatives in parentheses.
 * - null/undefined: empty string.
 * - any other unit: `null` (caller should fall back to `fmtValue`).
 */
export function fmtStatementValue(
  value: number | null | undefined,
  unit: string,
): string | null {
  if (value === null || value === undefined) return "";

  if (unit === "USD_per_share") {
    const negative = value < 0;
    return parenIfNegative(Math.abs(value).toFixed(2), negative);
  }

  if (MONEY_UNITS.has(unit)) {
    const negative = value < 0;
    const whole = Math.round(Math.abs(value));
    return parenIfNegative(whole.toLocaleString("en-US"), negative);
  }

  return null;
}
