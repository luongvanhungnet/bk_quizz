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

  it("falls back to a readable label for non-batch stages", () => {
    expect(describeQuizBatchStatus("COMMITTING", null).label).toBe(
      "Đang lưu toàn bộ câu hỏi",
    );
  });
});
