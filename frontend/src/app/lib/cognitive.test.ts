import { describe, expect, it } from "vitest";
import { cognitiveDistribution, cognitiveLabel } from "./cognitive";

describe("cognitive levels", () => {
  it("distributes forty balanced questions using the canonical weights", () => {
    expect(cognitiveDistribution(40)).toEqual({
      L1: 4,
      L2: 10,
      L3: 14,
      L4: 10,
      L5: 2,
    });
    expect(cognitiveLabel("BALANCED")).toBe("Cân bằng");
  });
});
