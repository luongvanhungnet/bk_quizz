import { describe, expect, it } from "vitest";
import { adaptivePollInterval } from "./polling";

describe("adaptivePollInterval", () => {
  it("backs off, stops for terminal state, and pauses in a hidden tab", () => {
    expect(adaptivePollInterval(0, false, false)).toBe(2_000);
    expect(adaptivePollInterval(2, false, false)).toBe(5_000);
    expect(adaptivePollInterval(5, false, false)).toBe(10_000);
    expect(adaptivePollInterval(5, true, false)).toBe(false);
    expect(adaptivePollInterval(1, false, true)).toBe(false);
  });
});
