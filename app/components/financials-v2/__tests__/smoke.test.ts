import { describe, it, expect } from "vitest";

// Smoke test: confirms the vitest runner + TS + esbuild pipeline works and can
// import the financials-v2 module graph (which pulls in React + ./types +
// ./constants). If this passes, Tasks 11-13 can write real buildMatrix/formatter
// tests. (Set up at the "vitest gate", 2026-06-04.)
describe("vitest setup smoke", () => {
  it("runs and does arithmetic", () => {
    expect(1 + 1).toBe(2);
  });

  it("can import buildMatrix from useFinancialMatrix without crashing", async () => {
    const mod = await import("../useFinancialMatrix");
    expect(typeof mod.buildMatrix).toBe("function");
  });
});
