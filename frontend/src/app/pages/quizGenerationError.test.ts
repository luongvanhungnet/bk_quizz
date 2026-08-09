import { describe, expect, it } from "vitest";
import { describeQuizGenerationError } from "./quizGenerationError";

describe("describeQuizGenerationError", () => {
  it("does not mislabel a generic validation failure as a cognitive contract error", () => {
    expect(describeQuizGenerationError("VALIDATION_ERROR")).toEqual({
      title: "Dữ liệu sinh quiz không hợp lệ",
      message:
        "Dịch vụ RAG đã từ chối một trường dữ liệu trong yêu cầu. Xem nhật ký để biết field cụ thể trước khi thử lại.",
      action: "RETRY",
    });
  });

  it("explains an incompatible RAG generation contract", () => {
    expect(describeQuizGenerationError("RAG_CONTRACT_MISMATCH")).toEqual({
      title: "Backend và RAG chưa cùng phiên bản",
      message:
        "Quiz và tài liệu vẫn được giữ nguyên. Hãy khởi động lại hoặc cập nhật dịch vụ RAG rồi thử lại tác vụ hiện tại.",
      action: "RETRY",
    });
  });

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

  it("explains Cognitive contract errors and lets failed jobs retry", () => {
    for (const code of [
      "COGNITIVE_PLAN_INVALID",
      "COGNITIVE_CHECKPOINT_INVALID",
    ]) {
      expect(describeQuizGenerationError(code)).toEqual({
        title: "Cấu hình mức độ tư duy chưa đồng bộ",
        message:
          "Backend và dịch vụ RAG đã nhận cấu hình Cognitive Level không tương thích. Cấu hình quiz vẫn được giữ nguyên; hãy thử lại sau khi các dịch vụ được cập nhật.",
        action: "RETRY",
      });
    }
  });

  it("explains a cognitive quality failure without calling it an AI outage", () => {
    const result = describeQuizGenerationError(
      "COGNITIVE_CONSTRAINT_VIOLATION",
    );

    expect(result.title).toBe("Chưa đủ câu đạt mức độ tư duy");
    expect(result.message).toContain("câu chưa đạt");
    expect(result.message).not.toContain("dịch vụ AI");
    expect(result.action).toBe("ADJUST");
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

  it("distinguishes provider request incompatibility from grounding errors", () => {
    for (const code of [
      "GEMINI_API_REQUEST_INCOMPATIBLE",
      "GEMINI_OAUTH_REQUEST_INCOMPATIBLE",
      "LLM_PROVIDER_REQUEST_INCOMPATIBLE",
    ]) {
      const description = describeQuizGenerationError(code);
      expect(description.title).toContain("nhà cung cấp AI");
      expect(description.action).toBe("RETRY");
    }
  });

  it("describes an internal RAG failure without blaming Gemini or offering blind retry", () => {
    const description = describeQuizGenerationError("RAG_INTERNAL_ERROR");

    expect(description.title).toBe("RAG gặp lỗi nội bộ");
    expect(description.message).toContain("giai đoạn");
    expect(description.message).not.toContain("Gemini");
    expect(description.action).toBeNull();
  });
});
