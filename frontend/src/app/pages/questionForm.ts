import type { CognitiveLevel, Question, QuestionType } from "../../api/bkquiz";

export interface QuestionFormState {
  type: QuestionType;
  prompt: string;
  explanation: string;
  points: string;
  cognitiveLevel: CognitiveLevel;
  options: string[];
  correct: number[];
  answers: string;
}

export function questionToFormState(question: Question): QuestionFormState {
  return {
    type: question.type,
    prompt: question.prompt,
    explanation: question.explanation ?? "",
    points: String(question.points),
    cognitiveLevel: question.cognitiveLevel,
    options: question.options.map((option) => option.text),
    correct: question.options.flatMap((option, index) => option.correct ? [index] : []),
    answers: question.acceptedAnswers.join("\n"),
  };
}

export function questionFormToRequest(form: QuestionFormState) {
  return {
    type: form.type,
    prompt: form.prompt.trim(),
    explanation: form.explanation.trim() || null,
    points: Number(form.points),
    cognitiveLevel: form.cognitiveLevel,
    complexityProfile: null,
    sourceChunkId: null,
    options: form.type === "FILL_BLANK" ? [] : form.options.map((text, index) => ({
      text: text.trim(),
      correct: form.correct.includes(index),
    })),
    acceptedAnswers: form.type === "FILL_BLANK"
      ? form.answers.split("\n").map((answer) => answer.trim()).filter(Boolean)
      : [],
  };
}
