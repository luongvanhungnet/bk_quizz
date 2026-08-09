import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  QuizGenerationTimeline,
  mergeJobEvents,
} from "./QuizGenerationTimeline";

describe("QuizGenerationTimeline", () => {
  it("shows the exact safe validation field returned by RAG", () => {
    render(
      <QuizGenerationTimeline
        events={[
          {
            id: 4,
            jobId: "job-1",
            occurredAt: "2026-08-07T15:36:10Z",
            level: "ERROR",
            code: "VALIDATION_ERROR",
            message: "Dữ liệu gửi lên không hợp lệ.",
            progress: null,
            provider: null,
            batchIndex: null,
            partIndex: null,
            requestId: "job-1",
            metadata: {
              validationErrors: [
                {
                  field: "acceptedQuestions",
                  type: "list_type",
                  message: "Input should be a valid list",
                },
              ],
            },
          },
        ]}
      />,
    );

    expect(screen.getByRole("listitem")).toHaveTextContent(
      "acceptedQuestions: phải là một danh sách.",
    );
  });

  it("merges cursor pages in order without duplicate events", () => {
    const event = (id: number) => ({
      id,
      jobId: "job-1",
      occurredAt: `2026-07-29T10:15:${id.toString().padStart(2, "0")}Z`,
      level: "INFO" as const,
      code: "STEP",
      message: `Step ${id}`,
      progress: id,
      provider: null,
      batchIndex: null,
      partIndex: null,
      requestId: null,
      metadata: {},
    });

    expect(mergeJobEvents([event(1), event(2)], [event(2), event(3)]))
      .toEqual([event(1), event(2), event(3)]);
  });

  it("renders timestamp, provider fallback, and error details", () => {
    render(
      <QuizGenerationTimeline
        events={[
          {
            id: 1,
            jobId: "job-1",
            occurredAt: "2026-07-29T10:15:30Z",
            level: "WARNING",
            code: "FALLBACK_STARTED",
            message:
              "Gemini không thể hoàn tất yêu cầu. Đang chuyển sang Ollama Qwen.",
            progress: 35,
            provider: "ollama",
            batchIndex: 0,
            partIndex: null,
            requestId: "rag-request-1",
            metadata: {},
          },
        ]}
      />,
    );

    expect(screen.getByText("Nhật ký tạo Quiz")).toBeInTheDocument();
    expect(
      screen.getByText(/Đang chuyển sang Ollama Qwen/),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Ollama Qwen/)).toHaveLength(2);
    expect(screen.getByText(/rag-request-1/)).toBeInTheDocument();
  });

  it("does not render NaN labels for omitted or invalid indexes", () => {
    render(
      <QuizGenerationTimeline
        events={[
          {
            id: 1,
            jobId: "job-1",
            occurredAt: "2026-07-29T10:15:30Z",
            level: "INFO",
            code: "WORKER_STARTED",
            message: "Bộ xử lý đã bắt đầu tạo quiz.",
            progress: null,
            provider: null,
            requestId: null,
            metadata: {},
          },
          {
            id: 2,
            jobId: "job-1",
            occurredAt: "2026-07-29T10:15:31Z",
            level: "INFO",
            code: "PART_STARTED",
            message: "Đang tạo phần hợp lệ.",
            progress: null,
            provider: "gemini_api_key",
            batchIndex: 0,
            partIndex: 0,
            requestId: null,
            metadata: {},
          },
        ]}
      />,
    );

    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
    expect(screen.getByText("Nhóm 1")).toBeInTheDocument();
    expect(screen.getByText("Phần 1")).toBeInTheDocument();
  });

  it("renders a safe cognitive validation summary without question content", () => {
    render(
      <QuizGenerationTimeline
        events={[{
          id: 3,
          jobId: "job-1",
          occurredAt: "2026-08-07T13:35:42Z",
          level: "WARNING",
          code: "COGNITIVE_VALIDATION_SUMMARY",
          message: "6/10 câu đạt mức độ tư duy; 4 câu cần điều chỉnh.",
          progress: 50,
          provider: null,
          batchIndex: 0,
          partIndex: null,
          requestId: null,
          metadata: {
            acceptedQuestions: 6,
            rejectedQuestions: 4,
            failureDistribution: {
              NOVEL_SCENARIO_REQUIRED: 3,
              SCORE_OUT_OF_RANGE: 1,
            },
          },
        }]}
      />,
    );

    expect(screen.getByText(/Đạt 6/)).toBeInTheDocument();
    expect(screen.getByText(/Cần điều chỉnh 4/)).toBeInTheDocument();
    expect(screen.getByText(/Thiếu tình huống mới: 3/)).toBeInTheDocument();
    expect(screen.getByText(/Điểm phức tạp ngoài khoảng: 1/)).toBeInTheDocument();
  });

  it("renders citation matching progress without exposing document text", () => {
    render(
      <QuizGenerationTimeline
        events={[{
          id: 5,
          jobId: "job-1",
          occurredAt: "2026-08-08T00:35:42Z",
          level: "WARNING",
          code: "CITATION_VALIDATION_SUMMARY",
          message: "Đã đối chiếu nguồn cho 18/20 câu.",
          progress: 70,
          provider: null,
          batchIndex: 0,
          partIndex: null,
          requestId: "request-1",
          metadata: {
            semanticSameSource: 4,
            semanticCrossSource: 1,
            dropped: 2,
            invalidCitations: 3,
          },
        }]}
      />,
    );

    expect(screen.getByText(/Ánh xạ ngữ nghĩa 5/)).toBeInTheDocument();
    expect(screen.getByText(/Bỏ citation phụ lỗi 2/)).toBeInTheDocument();
    expect(screen.getByText(/Còn thiếu 3 citation/)).toBeInTheDocument();
  });

  it("renders the safe stage and diagnostic id for an internal RAG failure", () => {
    render(
      <QuizGenerationTimeline
        events={[{
          id: 6,
          jobId: "job-1",
          occurredAt: "2026-08-08T05:20:47Z",
          level: "ERROR",
          code: "RAG_INTERNAL_ERROR",
          message: "RAG gặp lỗi nội bộ khi xử lý kết quả quiz.",
          progress: 70,
          provider: null,
          batchIndex: 0,
          partIndex: null,
          requestId: "job-1",
          metadata: {
            stage: "MATCHING_CITATIONS",
            errorId: "rag-error-456",
          },
        }]}
      />,
    );

    expect(screen.getByText(/Giai đoạn: MATCHING_CITATIONS/)).toBeInTheDocument();
    expect(screen.getByText(/Mã tra cứu: rag-error-456/)).toBeInTheDocument();
  });
});
