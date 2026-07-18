import { describe, expect, it } from "vitest";
import { ApiRequestError } from "../../api/client";
import { formatClassroomJoinError } from "./classroomJoinError";

describe("formatClassroomJoinError", () => {
  it("replaces a generic server error with classroom context and trace id", () => {
    const error = new ApiRequestError(500, {
      success: false,
      message: "Hệ thống đang gặp sự cố. Vui lòng thử lại sau.",
      data: undefined,
      errors: [{ code: "INTERNAL_ERROR", message: "Hệ thống đang gặp sự cố. Vui lòng thử lại sau." }],
      traceId: "join-trace-456",
    });

    expect(formatClassroomJoinError(error)).toBe(
      "Không thể hoàn tất việc tham gia lớp học do lỗi máy chủ. Mã yêu cầu: join-trace-456",
    );
  });
});
