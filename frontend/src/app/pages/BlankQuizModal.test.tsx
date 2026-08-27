import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { bkquizApi } from "../../api/bkquiz";
import { BlankQuizModal } from "./BlankQuizModal";

describe("BlankQuizModal", () => {
  it("creates an empty balanced quiz without calling AI generation", async () => {
    const quiz = {
      id: "quiz-1",
      topicId: "topic-1",
      title: "Quiz trống",
      status: "DRAFT",
      questionCount: 0,
    };
    const create = vi.spyOn(bkquizApi, "createQuiz").mockResolvedValue(quiz as never);
    const generate = vi.spyOn(bkquizApi, "generateQuiz");
    const onCreated = vi.fn();

    render(
      <BlankQuizModal
        topicId="topic-1"
        onClose={vi.fn()}
        onCreated={onCreated}
      />,
    );
    fireEvent.change(screen.getByLabelText("Tên quiz"), {
      target: { value: "Quiz trống" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Tạo quiz trống" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(quiz));
    expect(create).toHaveBeenCalledWith(expect.objectContaining({
      topicId: "topic-1",
      cognitiveMode: "BALANCED",
    }));
    expect(generate).not.toHaveBeenCalled();
  });
});
