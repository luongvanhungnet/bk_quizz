import type { ApiErrorDetail } from "../../api/client";

export const QUESTION_IMPORT_MAX_BYTES = 5 * 1024 * 1024;

export function validateQuestionImportFile(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".xlsx")) {
    return "Chỉ chấp nhận file Excel có phần mở rộng .xlsx.";
  }
  if (file.size === 0) return "File Excel đang trống.";
  if (file.size > QUESTION_IMPORT_MAX_BYTES) return "File Excel không được vượt quá 5 MB.";
  return null;
}

export interface QuestionImportErrorGroup {
  location: string;
  errors: ApiErrorDetail[];
}

export function groupQuestionImportErrors(details: ApiErrorDetail[]): QuestionImportErrorGroup[] {
  const groups = new Map<string, ApiErrorDetail[]>();
  for (const detail of details) {
    const location = detail.field?.trim() || "File Excel";
    const values = groups.get(location) ?? [];
    values.push(detail);
    groups.set(location, values);
  }
  return Array.from(groups, ([location, errors]) => ({ location, errors }));
}
