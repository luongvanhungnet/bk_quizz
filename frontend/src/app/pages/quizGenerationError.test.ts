import { describe, expect, it } from "vitest";
import { describeQuizGenerationError } from "./quizGenerationError";

describe("describeQuizGenerationError", () => {
  it("offers reindex for an inconsistent RAG index", () => {
    expect(describeQuizGenerationError("RAG_INDEX_INCONSISTENT")).toEqual({
      title: "Chỉ mục tài liệu không nhất quán",
      message:
        "Tài liệu đã được lưu nhưng chỉ mục không còn đủ dữ liệu. Hãy lập chỉ mục lại rồi sinh quiz.",
      action: "REINDEX",
    });
  });

  it("offers configuration adjustment for insufficient document text", () => {
    expect(
      describeQuizGenerationError("RAG_DOCUMENT_TEXT_INSUFFICIENT").action,
    ).toBe("ADJUST");
  });

  it("offers retry for temporary or malformed AI output", () => {
    expect(describeQuizGenerationError("GROUNDED_QUIZ_INVALID").action).toBe(
      "RETRY",
    );
  });

  it("distinguishes question difficulty, citation, and persistence failures", () => {
    expect(describeQuizGenerationError("QUESTION_DIFFICULTY_INVALID").action).toBe(
      "ADJUST",
    );
    expect(describeQuizGenerationError("INVALID_CITATION_QUOTE").title).toContain(
      "trích dẫn",
    );
    expect(describeQuizGenerationError("QUIZ_PERSISTENCE_FAILED").title).toContain(
      "lưu quiz",
    );
  });
});
