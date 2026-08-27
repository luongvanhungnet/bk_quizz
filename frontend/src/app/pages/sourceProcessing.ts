export interface SourceProcessingInput {
  status: string;
  indexingStep: string | null;
  processingStage?: string;
  indexingProgress: number;
  processingDelayed: boolean;
  processorAvailable: boolean;
}

export interface SourceProcessingDescription {
  label: string;
  warning: string | undefined;
}

export function shouldShowReindexAction(source: {
  status: string;
  indexingStep: string | null;
  indexedAt?: string | null;
  mathExtractionStatus?: string;
}): boolean {
  return source.status === "FAILED"
    || source.indexingStep === "REINDEX_FAILED"
    || (source.status === "READY" && (
      !source.indexedAt
      || source.mathExtractionStatus === "PARTIAL"
      || source.mathExtractionStatus === "FAILED"
    ));
}

export function describeSourceProcessing(
  source: SourceProcessingInput,
): SourceProcessingDescription {
  const processing = !["READY", "FAILED", "DELETED"].includes(source.status);
  const stage = source.processingStage ?? source.indexingStep ?? source.status;
  if (stage === "REINDEX_FAILED" && source.status === "READY") {
    return {
      label: "Sẵn sàng với chỉ mục trước đó",
      warning: "Lập chỉ mục lại thất bại; phiên bản trước vẫn có thể sử dụng.",
    };
  }
  if (stage === "QUEUED" && source.status !== "UPLOADED") {
    const warning = !source.processorAvailable
      ? "Bộ xử lý RAG chưa hoạt động. Tài liệu đã được lưu và sẽ tự tiếp tục khi worker được khởi động."
      : source.processingDelayed
        ? "Tài liệu đang chờ đến lượt xử lý. Bạn không cần tải lại tệp."
        : undefined;
    return { label: "Đã tải lên, đang chờ bộ xử lý RAG", warning };
  }
  const warning =
    processing && (!source.processorAvailable || source.processingDelayed)
      ? "Bộ xử lý tài liệu chưa hoạt động hoặc đang quá tải. Tài liệu đã được lưu và sẽ tự tiếp tục khi dịch vụ hoạt động."
      : undefined;
  if (source.status === "UPLOADED" || source.indexingStep === "QUEUED") {
    return { label: "Đã tải lên, đang chờ bộ xử lý", warning };
  }
  const labels: Record<string, string> = {
    REINDEX_QUEUED: "Đang xử lý lại tài liệu",
    UPLOADING_TO_RAG: "Đang chuyển tài liệu sang dịch vụ phân tích",
    VALIDATING: "Đang kiểm tra tệp",
    PARSING: "Đang đọc nội dung tài liệu",
    CHUNKING: "Đang chia tài liệu thành các đoạn",
    EMBEDDING: "Đang tạo chỉ mục tìm kiếm",
    SYNCING: "Đang đồng bộ kết quả",
    READY: "Sẵn sàng để sinh quiz",
    FAILED: "Xử lý tài liệu thất bại",
  };
  return { label: labels[stage] ?? "Đang xử lý tài liệu", warning };
}
