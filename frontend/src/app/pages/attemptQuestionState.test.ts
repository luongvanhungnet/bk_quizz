import { describe, expect, it } from "vitest";
import { questionVisualState } from "./attemptQuestionState";

describe("questionVisualState", () => {
  it("prioritizes confirmed live feedback over draft and saved states", () => {
    expect(
      questionVisualState({
        hasAnswer: true,
        dirty: false,
        saved: true,
        confirmedCorrect: false,
      }),
    ).toBe("CONFIRMED_INCORRECT");
  });
});
