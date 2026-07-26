import { describe, expect, it } from "vitest";
import { getAssignmentAvailability } from "./sharedResourceAvailability";

describe("getAssignmentAvailability", () => {
  it("explains when a published assignment has not opened yet", () => {
    expect(
      getAssignmentAvailability(
        {
          status: "PUBLISHED",
          opensAt: "2026-08-01T08:00:00.000Z",
          dueAt: null,
        },
        new Date("2026-08-01T07:00:00.000Z").getTime(),
      ),
    ).toEqual({
      available: false,
      reason: "Bài mở lúc 15:00 01/08/2026.",
    });
  });
});
