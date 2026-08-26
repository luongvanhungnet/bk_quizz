export const MAX_QUESTIONS_PER_QUIZ = 100;

export function remainingQuestionCapacity(questionCount: number): number {
  return Math.max(0, MAX_QUESTIONS_PER_QUIZ - questionCount);
}
