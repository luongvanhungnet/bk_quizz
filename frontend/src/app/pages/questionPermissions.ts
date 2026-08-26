import type { QuizStatus } from "../../api/bkquiz";

const QUESTION_MANAGEMENT_STATUSES: ReadonlySet<QuizStatus> = new Set([
  "DRAFT",
  "READY",
  "PUBLISHED",
]);

export function canManageQuizQuestions(status: QuizStatus): boolean {
  return QUESTION_MANAGEMENT_STATUSES.has(status);
}
