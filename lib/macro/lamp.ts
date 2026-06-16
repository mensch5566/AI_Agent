import type { Lamp, Polarity } from "./types";

/**
 * v1 lamp rule (spec §5): 本期 vs 上一期 + polarity.
 * green = bull (往好方向), red = bear (往壞方向), grey = 無資料/無前值/持平.
 */
export function computeLamp(
  curr: number | null,
  prev: number | null,
  polarity: Polarity,
): Lamp {
  if (curr === null || prev === null || curr === prev) {
    return { color: "grey", curr, prev, polarity, basis: "無資料/無前值/持平" };
  }
  const rose = curr > prev;
  const good = polarity === "higher_better" ? rose : !rose;
  return {
    color: good ? "green" : "red",
    curr,
    prev,
    polarity,
    basis: `${prev} → ${curr}（${polarity}）→ ${good ? "bull" : "bear"}`,
  };
}
