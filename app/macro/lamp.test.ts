import { describe, it, expect } from "vitest";
// 相對 import 避免 vitest 未設 @/ alias 而解析失敗
import { computeLamp } from "../../lib/macro/lamp";

describe("computeLamp", () => {
  it("higher_better: 上升 => green (bull)", () => {
    expect(computeLamp(110, 100, "higher_better").color).toBe("green");
  });
  it("higher_better: 下降 => red (bear)", () => {
    expect(computeLamp(90, 100, "higher_better").color).toBe("red");
  });
  it("lower_better (CDS/OAS 上升=壞): 上升 => red", () => {
    expect(computeLamp(6.1, 5.9, "lower_better").color).toBe("red");
  });
  it("lower_better: 下降 => green", () => {
    expect(computeLamp(5.7, 5.9, "lower_better").color).toBe("green");
  });
  it("持平 => grey", () => {
    expect(computeLamp(100, 100, "higher_better").color).toBe("grey");
  });
  it("無前值 => grey", () => {
    expect(computeLamp(100, null, "higher_better").color).toBe("grey");
  });
  it("無資料 => grey", () => {
    expect(computeLamp(null, null, "higher_better").color).toBe("grey");
  });
});
