import { describe, expect, it } from "vitest";
import { describeAiValidationWarning, describeCitationWarningRole } from "./aiValidation";

describe("describeAiValidationWarning", () => {
  it("turns AI quality codes into owner-facing warnings", () => {
    expect(describeAiValidationWarning("LEVEL_MISMATCH")).toBe(
      "Chưa đạt mức độ tư duy đã chọn",
    );
    expect(describeAiValidationWarning("INVALID_CITATION_QUOTE")).toBe(
      "Thiếu nguồn trích dẫn đã xác minh",
    );
    expect(describeAiValidationWarning("DUPLICATE_QUESTION_PROMPT")).toBe(
      "Có thể trùng nội dung câu hỏi khác",
    );
  });
});

describe("describeCitationWarningRole", () => {
  it("distinguishes question, answer, and explanation citation warnings", () => {
    expect(describeCitationWarningRole("QUESTION")).toBe("Nguồn câu hỏi chưa được xác minh");
    expect(describeCitationWarningRole("ANSWER")).toBe("Nguồn đáp án chưa được xác minh");
    expect(describeCitationWarningRole("EXPLANATION")).toBe("Nguồn giải thích chưa được xác minh");
  });
});
