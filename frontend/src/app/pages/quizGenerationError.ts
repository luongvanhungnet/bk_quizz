export type QuizGenerationErrorAction = "REINDEX" | "ADJUST" | "RETRY" | null;

export interface QuizGenerationErrorDescription {
  title: string;
  message: string;
  action: QuizGenerationErrorAction;
}

const cognitiveContractError: QuizGenerationErrorDescription = {
  title: "Cấu hình mức độ tư duy chưa đồng bộ",
  message:
    "Backend và dịch vụ RAG đã nhận cấu hình Cognitive Level không tương thích. Cấu hình quiz vẫn được giữ nguyên; hãy thử lại sau khi các dịch vụ được cập nhật.",
  action: "RETRY",
};

const providerRequestError: QuizGenerationErrorDescription = {
  title: "Yêu cầu chưa tương thích với nhà cung cấp AI",
  message:
    "Quiz và tài liệu vẫn được giữ nguyên. Hệ thống đã thử các nhà cung cấp khả dụng nhưng chưa thể xử lý cấu hình hiện tại.",
  action: "RETRY",
};

const descriptions: Record<string, QuizGenerationErrorDescription> = {
  GEMINI_API_REQUEST_INCOMPATIBLE: providerRequestError,
  GEMINI_OAUTH_REQUEST_INCOMPATIBLE: providerRequestError,
  LLM_PROVIDER_REQUEST_INCOMPATIBLE: providerRequestError,
  COGNITIVE_PLAN_INVALID: cognitiveContractError,
  COGNITIVE_CHECKPOINT_INVALID: cognitiveContractError,
  VALIDATION_ERROR: {
    title: "Dữ liệu sinh quiz không hợp lệ",
    message:
      "Dịch vụ RAG đã từ chối một trường dữ liệu trong yêu cầu. Xem nhật ký để biết field cụ thể trước khi thử lại.",
    action: "RETRY",
  },
  RAG_CONTRACT_MISMATCH: {
    title: "Backend và RAG chưa cùng phiên bản",
    message:
      "Quiz và tài liệu vẫn được giữ nguyên. Hãy khởi động lại hoặc cập nhật dịch vụ RAG rồi thử lại tác vụ hiện tại.",
    action: "RETRY",
  },
  COGNITIVE_CONSTRAINT_VIOLATION: {
    title: "Chưa đủ câu đạt mức độ tư duy",
    message:
      "Một số câu chưa đạt các ràng buộc định lượng của mức tư duy đã chọn. Hãy chọn thêm tài liệu, giảm mức tư duy hoặc thử sinh lại trên cùng quiz.",
    action: "ADJUST",
  },
  QUESTION_DIFFICULTY_INVALID: {
    title: "Độ khó câu hỏi không hợp lệ",
    message:
      "Quiz vẫn giữ cấu hình ban đầu. Hãy điều chỉnh độ khó hoặc thử lại sau khi backend được cập nhật.",
    action: "ADJUST",
  },
  INVALID_CITATION_QUOTE: {
    title: "Một số câu chưa có trích dẫn đủ chắc chắn",
    message:
      "BKQuiz đã giữ các câu có nguồn hợp lệ và sẽ chỉ tạo lại phần còn thiếu. Bạn không cần tải lại tài liệu.",
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
  RAG_INTERNAL_ERROR: {
    title: "RAG gặp lỗi nội bộ",
    message:
      "Tác vụ dừng tại một giai đoạn xử lý nội bộ. Hãy gửi mã lỗi, mã yêu cầu và mã tra cứu trong timeline cho quản trị viên trước khi chạy lại.",
    action: null,
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
