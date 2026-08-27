import type { Question } from "../../api/bkquiz";
import { questionFormToRequest, questionToFormState } from "./questionForm";

describe("questionToFormState", () => {
  it("prefills the edit form from the selected question", () => {
    const question = {
      id: "question-1",
      quizId: "quiz-1",
      type: "MULTIPLE_SELECT",
      prompt: "Chọn các đáp án đúng",
      explanation: "Giải thích",
      points: 2.5,
      position: 0,
      difficulty: "MEDIUM",
      cognitiveLevel: "L2",
      complexityProfile: null,
      complexityScore: null,
      options: [
        { id: "option-1", text: "A", correct: true, position: 0 },
        { id: "option-2", text: "B", correct: false, position: 1 },
        { id: "option-3", text: "C", correct: true, position: 2 },
      ],
      acceptedAnswers: [],
      citations: [],
      version: 3,
    } satisfies Question;

    expect(questionToFormState(question)).toEqual({
      type: "MULTIPLE_SELECT",
      prompt: "Chọn các đáp án đúng",
      explanation: "Giải thích",
      points: "2.5",
      cognitiveLevel: "L2",
      options: ["A", "B", "C"],
      correct: [0, 2],
      answers: "",
    });
  });

  it("builds an update request without stale AI source metadata", () => {
    expect(questionFormToRequest({
      type: "SINGLE_CHOICE",
      prompt: "  Nội dung đã sửa  ",
      explanation: "  Giải thích mới  ",
      points: "2",
      cognitiveLevel: "L4",
      options: ["Đúng", "Sai"],
      correct: [1],
      answers: "",
    })).toEqual({
      type: "SINGLE_CHOICE",
      prompt: "Nội dung đã sửa",
      explanation: "Giải thích mới",
      points: 2,
      cognitiveLevel: "L4",
      complexityProfile: null,
      sourceChunkId: null,
      options: [
        { text: "Đúng", correct: false },
        { text: "Sai", correct: true },
      ],
      acceptedAnswers: [],
    });
  });
});
