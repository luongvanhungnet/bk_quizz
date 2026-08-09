const labels: Record<string, string> = {
  LEVEL_MISMATCH: "Chưa đạt mức độ tư duy đã chọn",
  CONCEPT_COUNT_OUT_OF_RANGE: "Số khái niệm chưa đúng yêu cầu",
  REASONING_STEPS_OUT_OF_RANGE: "Số bước suy luận chưa đúng yêu cầu",
  NOVEL_SCENARIO_REQUIRED: "Thiếu tình huống mới",
  COMPARISON_REQUIRED: "Thiếu yêu cầu so sánh hoặc tổng hợp",
  SCORE_OUT_OF_RANGE: "Điểm phức tạp chưa đúng mức đã chọn",
  INVALID_CITATION_QUOTE: "Thiếu nguồn trích dẫn đã xác minh",
  DUPLICATE_QUESTION_PROMPT: "Có thể trùng nội dung câu hỏi khác",
  QUESTION_COUNT_INCOMPLETE: "Số câu tạo được ít hơn yêu cầu",
  MATH_FORMAT_UNVERIFIED: "Định dạng công thức toán cần được kiểm tra",
};

const qualityCodes = new Set([
  ...Object.keys(labels),
  "COGNITIVE_CONSTRAINT_VIOLATION",
]);

export function describeAiValidationWarning(code: string): string {
  return labels[code] ?? "Kết quả AI cần được chủ Quiz kiểm tra";
}

export function describeCitationWarningRole(role: string | null | undefined): string {
  switch (role) {
    case "QUESTION":
      return "Nguồn câu hỏi chưa được xác minh";
    case "ANSWER":
      return "Nguồn đáp án chưa được xác minh";
    case "EXPLANATION":
      return "Nguồn giải thích chưa được xác minh";
    default:
      return "Nguồn trích dẫn chưa được xác minh";
  }
}

export function isAiQualityWarningCode(code: string | null | undefined): boolean {
  return Boolean(code && qualityCodes.has(code));
}
