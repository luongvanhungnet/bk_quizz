import { ApiRequestError } from "../../api/client";

export function formatClassroomJoinError(error: unknown): string {
  if (!(error instanceof ApiRequestError)) {
    return error instanceof Error ? error.message : "Không thể tham gia lớp học.";
  }

  const trace = error.traceId ? ` Mã yêu cầu: ${error.traceId}` : "";
  if (error.code === "INTERNAL_ERROR") {
    return `Không thể hoàn tất việc tham gia lớp học do lỗi máy chủ.${trace}`;
  }
  return `${error.message}${trace}`;
}
