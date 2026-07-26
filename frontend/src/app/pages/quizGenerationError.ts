export type QuizGenerationErrorAction = "REINDEX" | "ADJUST" | "RETRY" | null;

export interface QuizGenerationErrorDescription {
  title: string;
  message: string;
  action: QuizGenerationErrorAction;
}

const descriptions: Record<string, QuizGenerationErrorDescription> = {
  QUESTION_DIFFICULTY_INVALID: {
    title: "Độ khó câu hỏi không hợp lệ",
    message:
      "Quiz vẫn giữ cấu hình ban đầu. Hãy điều chỉnh độ khó hoặc thử lại sau khi backend được cập nhật.",
    action: "ADJUST",
  },
  INVALID_CITATION_QUOTE: {
    title: "AI trích dẫn chưa khớp nguồn",
    message:
      "Câu hỏi chưa được lưu vì đoạn trích không khớp nguyên văn với tài liệu. Bạn có thể thử lại yêu cầu hiện tại.",
    action: "RETRY",
  },
  QUIZ_PERSISTENCE_FAILED: {
    title: "Backend lưu quiz thất bại",
    message:
      "Kết quả AI và cấu hình đang được giữ để thử lại mà không gọi Gemini thêm lần nữa.",
    action: "RETRY",
  },
  RAG_INDEX_INCONSISTENT: {
    title: "Chỉ mục tài liệu không nhất quán",
    message:
      "Tài liệu đã được lưu nhưng chỉ mục không còn đủ dữ liệu. Hãy lập chỉ mục lại rồi sinh quiz.",
    action: "REINDEX",
  },
  RAG_DOCUMENT_TEXT_INSUFFICIENT: {
    title: "Tài liệu có quá ít nội dung",
    message:
      "Hãy chọn thêm tài liệu có nội dung hữu ích trước khi sinh lại quiz.",
    action: "ADJUST",
  },
  RAG_CONTEXT_INSUFFICIENT: {
    title: "Chưa có đủ căn cứ để tạo câu hỏi",
    message:
      "Hãy chọn thêm tài liệu có nội dung phù hợp hoặc điều chỉnh số câu hỏi.",
    action: "ADJUST",
  },
  GROUNDED_QUIZ_INVALID: {
    title: "AI chưa tạo được quiz có nguồn hợp lệ",
    message:
      "Không có câu hỏi nào được lưu. Bạn có thể thử lại yêu cầu hiện tại.",
    action: "RETRY",
  },
  RAG_RATE_LIMITED: {
    title: "Dịch vụ AI đang giới hạn yêu cầu",
    message: "Vui lòng đợi một lúc rồi thử sinh lại quiz.",
    action: "RETRY",
  },
  RAG_UNAVAILABLE: {
    title: "Dịch vụ RAG chưa sẵn sàng",
    message:
      "Tài liệu và cấu hình quiz vẫn được giữ nguyên. Hãy thử lại khi dịch vụ hoạt động.",
    action: "RETRY",
  },
};

export function describeQuizGenerationError(
  code: string | null | undefined,
): QuizGenerationErrorDescription {
  if (code && descriptions[code]) return descriptions[code];
  return {
    title: "Không thể sinh quiz",
    message:
      "Tác vụ không hoàn tất. Hãy kiểm tra mã yêu cầu hoặc điều chỉnh cấu hình trước khi thử lại.",
    action: null,
  };
}
