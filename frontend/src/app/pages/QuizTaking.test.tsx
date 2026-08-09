import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { bkquizApi, type Attempt } from "../../api/bkquiz";
import QuizTaking from "./QuizTaking";

class IntersectionObserverStub {
  observe() {}
  disconnect() {}
  unobserve() {}
}

describe("QuizTaking", () => {
  beforeEach(() => {
    vi.stubGlobal("IntersectionObserver", IntersectionObserverStub);
    sessionStorage.clear();
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders every question vertically with a five-column navigator", async () => {
    const attempt: Attempt = {
      id: "attempt-1",
      quizId: "quiz-1",
      assignmentId: null,
      status: "IN_PROGRESS",
      startedAt: "2026-07-26T00:00:00Z",
      expiresAt: "2099-07-26T00:30:00Z",
      submittedAt: null,
      mode: "STANDARD",
      version: 0,
      answers: [],
      confirmedFeedback: [],
      questions: [
        {
          snapshotId: "question-1",
          type: "FILL_BLANK",
          prompt: "Câu hỏi thứ nhất",
          points: 1,
          position: 1,
          options: [],
        },
        {
          snapshotId: "question-2",
          type: "FILL_BLANK",
          prompt: "Câu hỏi thứ hai",
          points: 1,
          position: 2,
          options: [],
        },
      ],
    };
    vi.spyOn(bkquizApi, "attempt").mockResolvedValue(attempt);
    vi.spyOn(bkquizApi, "quiz").mockResolvedValue({
      id: "quiz-1",
      topicId: "topic-1",
      ownerId: "owner-1",
      title: "Quiz thử nghiệm",
      description: null,
      status: "PUBLISHED",
      visibility: "PUBLIC",
      generationMode: "MANUAL",
      difficulty: "EASY",
      cognitiveMode: "L1",
      durationMinutes: 30,
      questionCount: 2,
      errorCode: null,
      errorMessage: null,
      publishedAt: "2026-07-26T00:00:00Z",
      createdAt: "2026-07-26T00:00:00Z",
      updatedAt: "2026-07-26T00:00:00Z",
      version: 0,
    });
    vi.spyOn(bkquizApi, "preferences").mockResolvedValue({
      attemptAutosave: false,
      emailStudyReminders: true,
      publicProfile: false,
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { container } = render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/attempt/attempt-1"]}>
          <Routes>
            <Route path="/attempt/:attemptId" element={<QuizTaking />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Câu hỏi thứ nhất")).toBeInTheDocument();
    expect(screen.getByText("Câu hỏi thứ hai")).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Lưu câu trả lời" }),
    ).toHaveLength(2);
    expect(container.querySelector(".grid-cols-5")).toBeInTheDocument();
  });
});
