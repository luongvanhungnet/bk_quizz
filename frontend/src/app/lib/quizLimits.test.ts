import { describe, expect, it } from "vitest";
import {
  MAX_QUESTIONS_PER_QUIZ,
  remainingQuestionCapacity,
} from "./quizLimits";

describe("quiz question limit", () => {
  it("allows one hundred questions and calculates remaining capacity", () => {
    expect(MAX_QUESTIONS_PER_QUIZ).toBe(100);
    expect(remainingQuestionCapacity(99)).toBe(1);
    expect(remainingQuestionCapacity(100)).toBe(0);
  });
});
