import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { bkquizApi } from "../../api/bkquiz";
import { ApiRequestError } from "../../api/client";
import { QuestionImportModal } from "./QuestionImportModal";

describe("QuestionImportModal", () => {
  it("shows the format guide, examples, and template download action", () => {
    render(<QuestionImportModal quizId="quiz-1" onClose={() => undefined} onDone={async () => undefined} />);

    expect(screen.getByRole("heading", { name: "Import câu hỏi từ Excel" })).toBeInTheDocument();
    expect(screen.getByText("SINGLE_CHOICE")).toBeInTheDocument();
    expect(screen.getByText("MULTIPLE_SELECT")).toBeInTheDocument();
    expect(screen.getByText("FILL_BLANK")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tải file Excel mẫu" })).toBeInTheDocument();
  });

  it("keeps the modal open and shows every server error by Excel cell", async () => {
    vi.spyOn(bkquizApi, "importQuestions").mockRejectedValue(new ApiRequestError(422, {
      success: false,
      message: "File Excel có dữ liệu không hợp lệ.",
      data: null,
      traceId: "trace-excel",
      errors: [
        { code: "QUESTION_TYPE_INVALID", field: "CauHoi!A2", message: "Loại câu hỏi sai." },
        { code: "POINTS_INVALID", field: "CauHoi!J3", message: "Điểm không hợp lệ." },
      ],
    }));
    const user = userEvent.setup();
    render(<QuestionImportModal quizId="quiz-1" onClose={() => undefined} onDone={async () => undefined} />);

    await user.upload(screen.getByLabelText("Chọn file Excel cần import"), new File(["xlsx"], "questions.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }));
    await user.click(screen.getByRole("button", { name: "Import câu hỏi" }));

    expect(await screen.findByText("CauHoi!A2")).toBeInTheDocument();
    expect(screen.getByText("CauHoi!J3")).toBeInTheDocument();
    expect(screen.getByText("Mã yêu cầu: trace-excel")).toBeInTheDocument();
  });
});
