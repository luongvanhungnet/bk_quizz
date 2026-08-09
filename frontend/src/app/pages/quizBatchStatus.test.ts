import { describe, expect, it } from "vitest";
import { describeQuizBatchStatus } from "./quizBatchStatus";

describe("describeQuizBatchStatus", () => {
  it("shows the active batch and completed question count", () => {
    expect(
      describeQuizBatchStatus(
        "GENERATING_BATCH_2_OF_3_COMPLETED_4_OF_10",
        null,
      ),
    ).toEqual({
      label: "Đang tạo nhóm 2/3",
      detail: "Đã hoàn tất 4/10 câu hỏi",
    });
  });

  it("shows the automatic retry time for a failed Gemini batch", () => {
    const result = describeQuizBatchStatus(
      "WAITING_GEMINI_RETRY_2_OF_3_COMPLETED_4_OF_10",
      "2026-07-26T10:05:00Z",
      new Date("2026-07-26T10:00:00Z"),
    );

    expect(result.label).toBe("Gemini tạm lỗi, đang chờ thử lại nhóm 2/3");
    expect(result.detail).toContain("Đã hoàn tất 4/10 câu hỏi");
    expect(result.detail).toContain("Tự động thử lại lúc");
  });

  it("describes cognitive retry as question adjustment rather than an AI outage", () => {
    const result = describeQuizBatchStatus(
      "WAITING_COGNITIVE_RETRY_1_OF_1_COMPLETED_6_OF_10",
      "2026-08-07T13:40:00Z",
      new Date("2026-08-07T13:35:00Z"),
    );

    expect(result.label).toBe(
      "Các câu hỏi chưa đạt mức độ tư duy, đang chờ điều chỉnh nhóm 1/1",
    );
    expect(result.detail).toContain("Đã hoàn tất 6/10 câu hỏi");
    expect(result.detail).toContain("Tự động thử lại lúc");
  });

  it("describes citation retry without reporting a Gemini outage", () => {
    const result = describeQuizBatchStatus(
      "WAITING_CITATION_RETRY_1_OF_1_COMPLETED_18_OF_20",
      "2026-08-08T00:40:00Z",
      new Date("2026-08-08T00:35:00Z"),
    );

    expect(result.label).toBe(
      "Đang chờ bổ sung nguồn cho nhóm 1/1",
    );
    expect(result.detail).toContain("Đã hoàn tất 18/20 câu hỏi");
    expect(result.detail).toContain("Tự động thử lại lúc");
  });

  it("describes a transient RAG retry without blaming Gemini", () => {
    const result = describeQuizBatchStatus(
      "WAITING_RAG_RETRY_1_OF_1_COMPLETED_0_OF_20",
      "2026-08-08T06:25:00Z",
      new Date("2026-08-08T06:20:00Z"),
    );

    expect(result.label).toBe(
      "Dịch vụ xử lý tài liệu tạm gián đoạn, đang chờ thử lại nhóm 1/1",
    );
    expect(result.detail).toContain("Tự động thử lại lúc");
  });

  it("falls back to a readable label for non-batch stages", () => {
    expect(describeQuizBatchStatus("COMMITTING", null).label).toBe(
      "Đang lưu toàn bộ câu hỏi",
    );
  });
});
