export interface AssignmentAvailabilityInput {
  status: "DRAFT" | "PUBLISHED" | "CLOSED";
  opensAt: string | null;
  dueAt: string | null;
}

export interface AssignmentAvailability {
  available: boolean;
  reason?: string;
}

const formatDateTime = (value: string) =>
  new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour12: false,
  }).format(new Date(value));

export function getAssignmentAvailability(
  assignment: AssignmentAvailabilityInput,
  now = Date.now(),
): AssignmentAvailability {
  if (assignment.status === "CLOSED") {
    return { available: false, reason: "Bài đã đóng." };
  }
  if (assignment.status !== "PUBLISHED") {
    return { available: false, reason: "Bài chưa được xuất bản." };
  }
  if (assignment.opensAt && new Date(assignment.opensAt).getTime() > now) {
    return {
      available: false,
      reason: `Bài mở lúc ${formatDateTime(assignment.opensAt)}.`,
    };
  }
  if (assignment.dueAt && new Date(assignment.dueAt).getTime() <= now) {
    return { available: false, reason: "Bài đã quá hạn." };
  }
  return { available: true };
}
