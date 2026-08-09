export interface QuizBatchStatusDescription {
  label: string;
  detail?: string;
}

const BATCH_STEP =
  /^(GENERATING_BATCH|WAITING_NEXT_BATCH|WAITING_GEMINI_RETRY|WAITING_RAG_RETRY|WAITING_COGNITIVE_RETRY|WAITING_CITATION_RETRY|BATCH_FAILED)_(\d+)_OF_(\d+)_COMPLETED_(\d+)_OF_(\d+)$/;

export function describeQuizBatchStatus(
  step: string | null | undefined,
  availableAt: string | null | undefined,
  now = new Date(),
): QuizBatchStatusDescription {
  const match = step?.match(BATCH_STEP);
  if (match) {
    const stage = match[1]!;
    const batch = match[2]!;
    const totalBatches = match[3]!;
    const completed = match[4]!;
    const totalQuestions = match[5]!;
    const labels: Record<string, string> = {
      GENERATING_BATCH: `Đang tạo nhóm ${batch}/${totalBatches}`,
      WAITING_NEXT_BATCH: `Đang chờ tạo nhóm ${batch}/${totalBatches}`,
      WAITING_GEMINI_RETRY: `Gemini tạm lỗi, đang chờ thử lại nhóm ${batch}/${totalBatches}`,
      WAITING_RAG_RETRY: `Dịch vụ xử lý tài liệu tạm gián đoạn, đang chờ thử lại nhóm ${batch}/${totalBatches}`,
      WAITING_COGNITIVE_RETRY: `Các câu hỏi chưa đạt mức độ tư duy, đang chờ điều chỉnh nhóm ${batch}/${totalBatches}`,
      WAITING_CITATION_RETRY: `Đang chờ bổ sung nguồn cho nhóm ${batch}/${totalBatches}`,
      BATCH_FAILED: `Không thể tạo nhóm ${batch}/${totalBatches}`,
    };
    const details = [`Đã hoàn tất ${completed}/${totalQuestions} câu hỏi`];
    if (
      (stage === "WAITING_GEMINI_RETRY" ||
        stage === "WAITING_RAG_RETRY" ||
        stage === "WAITING_COGNITIVE_RETRY" ||
        stage === "WAITING_CITATION_RETRY") &&
      availableAt
    ) {
      const retryAt = new Date(availableAt);
      if (!Number.isNaN(retryAt.getTime()) && retryAt > now) {
        details.push(
          `Tự động thử lại lúc ${retryAt.toLocaleTimeString("vi-VN", {
            hour: "2-digit",
            minute: "2-digit",
          })}`,
        );
      }
    }
    return { label: labels[stage]!, detail: details.join(" · ") };
  }

  const labels: Record<string, string> = {
    QUEUED: "Đang chờ bộ xử lý",
    RETRIEVING: "Đang chuẩn bị tài liệu",
    VALIDATING_ALL_BATCHES: "Đang kiểm tra toàn bộ câu hỏi",
    COMMITTING: "Đang lưu toàn bộ câu hỏi",
    SUCCEEDED: "Đã tạo quiz thành công",
    FAILED: "Tạo quiz thất bại",
  };
  return { label: labels[step ?? "QUEUED"] ?? "Đang xử lý" };
}
