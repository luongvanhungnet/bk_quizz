import { canManageQuizQuestions } from "./questionPermissions";

describe("canManageQuizQuestions", () => {
  it("keeps edit and delete actions available for a published quiz", () => {
    expect(canManageQuizQuestions("PUBLISHED")).toBe(true);
  });
});
