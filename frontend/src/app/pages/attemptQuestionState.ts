export type QuestionVisualState =
  | "UNANSWERED"
  | "DIRTY"
  | "SAVED"
  | "CONFIRMED_CORRECT"
  | "CONFIRMED_INCORRECT";

export function questionVisualState(input: {
  hasAnswer: boolean;
  dirty: boolean;
  saved: boolean;
  confirmedCorrect?: boolean;
}): QuestionVisualState {
  if (input.confirmedCorrect === true) return "CONFIRMED_CORRECT";
  if (input.confirmedCorrect === false) return "CONFIRMED_INCORRECT";
  if (input.dirty) return "DIRTY";
  if (input.saved) return "SAVED";
  return input.hasAnswer ? "DIRTY" : "UNANSWERED";
}
