import { describe, expect, it } from "vitest";
import { describeSourceProcessing, shouldShowReindexAction } from "./sourceProcessing";

describe("describeSourceProcessing", () => {
  it("explains that a newly uploaded document is waiting for the processor", () => {
    expect(
      describeSourceProcessing({
        status: "UPLOADED",
        indexingStep: "QUEUED",
        indexingProgress: 0,
        processingDelayed: false,
        processorAvailable: true,
      }).label,
    ).toBe("Đã tải lên, đang chờ bộ xử lý");
  });

  it("keeps a persistent warning when the processor is unavailable", () => {
    const description = describeSourceProcessing({
      status: "UPLOADED",
      indexingStep: "QUEUED",
      indexingProgress: 0,
      processingDelayed: true,
      processorAvailable: false,
    });

    expect(description.warning).toBe(
      "Bộ xử lý tài liệu chưa hoạt động hoặc đang quá tải. Tài liệu đã được lưu và sẽ tự tiếp tục khi dịch vụ hoạt động.",
    );
  });

  it("uses Vietnamese labels for every processing stage", () => {
    const labels = [
      ["UPLOADING_TO_RAG", "Đang chuyển tài liệu sang dịch vụ phân tích"],
      ["PARSING", "Đang đọc nội dung tài liệu"],
      ["CHUNKING", "Đang chia tài liệu thành các đoạn"],
      ["EMBEDDING", "Đang tạo chỉ mục tìm kiếm"],
      ["SYNCING", "Đang đồng bộ kết quả"],
      ["READY", "Sẵn sàng để sinh quiz"],
      ["FAILED", "Xử lý tài liệu thất bại"],
    ] as const;

    for (const [processingStage, expected] of labels) {
      expect(
        describeSourceProcessing({
          status: processingStage,
          indexingStep: processingStage,
          indexingProgress: 50,
          processingDelayed: false,
          processorAvailable: true,
        }).label,
      ).toBe(expected);
    }
  });

  it("shows the RAG queue label when Spring is polling a pending RAG job", () => {
    const description = describeSourceProcessing({
      status: "EMBEDDING",
      indexingStep: "PENDING",
      processingStage: "QUEUED",
      indexingProgress: 0,
      processingDelayed: true,
      processorAvailable: false,
    });

    expect(description.label).toBe("Đã tải lên, đang chờ bộ xử lý RAG");
    expect(description.warning).toContain("Bộ xử lý RAG chưa hoạt động");
  });

  it("labels an in-place reindex without presenting it as a new upload", () => {
    const description = describeSourceProcessing({
      status: "EMBEDDING",
      indexingStep: "REINDEX_QUEUED",
      processingStage: "REINDEX_QUEUED",
      indexingProgress: 0,
      processingDelayed: false,
      processorAvailable: true,
    });

    expect(description.label).toBe("Đang xử lý lại tài liệu");
  });

  it("explains that the previous snapshot remains usable after reindex failure", () => {
    const description = describeSourceProcessing({
      status: "READY",
      indexingStep: "REINDEX_FAILED",
      processingStage: "REINDEX_FAILED",
      indexingProgress: 0,
      processingDelayed: false,
      processorAvailable: true,
    });

    expect(description.label).toBe("Sẵn sàng với chỉ mục trước đó");
    expect(description.warning).toBe(
      "Lập chỉ mục lại thất bại; phiên bản trước vẫn có thể sử dụng.",
    );
  });

  it("offers retry after an in-place reindex failure", () => {
    expect(shouldShowReindexAction({
      status: "READY",
      indexingStep: "REINDEX_FAILED",
      indexedAt: "2026-08-23T00:00:00Z",
      mathExtractionStatus: "NOT_DETECTED",
    })).toBe(true);
  });
});
