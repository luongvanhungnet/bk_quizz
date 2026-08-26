import { useState } from "react";
import { Download, FileSpreadsheet, Upload } from "lucide-react";
import { toast } from "sonner";
import { bkquizApi, type QuestionImportResult } from "../../api/bkquiz";
import { ApiRequestError } from "../../api/client";
import { Button, Modal } from "../components/ui";
import { MAX_QUESTIONS_PER_QUIZ } from "../lib/quizLimits";
import { groupQuestionImportErrors, validateQuestionImportFile } from "./questionImport";

export function QuestionImportModal({
  quizId,
  onClose,
  onDone,
}: {
  quizId: string;
  onClose: () => void;
  onDone: (result: QuestionImportResult) => Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<ApiRequestError | null>(null);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const downloadTemplate = async () => {
    setDownloading(true);
    setApiError(null);
    try {
      const blob = await bkquizApi.questionImportTemplate();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "BKQuiz-Mau-Import-Cau-Hoi.xlsx";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      if (error instanceof ApiRequestError) setApiError(error);
      else setLocalError(error instanceof Error ? error.message : "Không thể tải file Excel mẫu.");
    } finally {
      setDownloading(false);
    }
  };

  const submit = async () => {
    if (!file) {
      setLocalError("Hãy chọn file Excel .xlsx cần import.");
      return;
    }
    const validation = validateQuestionImportFile(file);
    if (validation) {
      setLocalError(validation);
      return;
    }
    setSaving(true);
    setLocalError(null);
    setApiError(null);
    try {
      const result = await bkquizApi.importQuestions(quizId, file);
      await onDone(result);
      toast.success(`Đã import ${result.importedCount} câu hỏi.`);
    } catch (error) {
      if (error instanceof ApiRequestError) setApiError(error);
      else setLocalError(error instanceof Error ? error.message : "Không thể import file Excel.");
    } finally {
      setSaving(false);
    }
  };

  const errorGroups = groupQuestionImportErrors(apiError?.details ?? []);
  return (
    <Modal title="Import câu hỏi từ Excel" onClose={onClose} className="max-w-5xl">
      <div className="max-h-[82vh] space-y-5 overflow-y-auto p-5">
        <section className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-950">
          <h4 className="font-bold">Định dạng file</h4>
          <ul className="mt-2 list-inside list-disc space-y-1">
            <li>Chỉ dùng file <b>.xlsx</b>, tối đa 5 MB và sheet <b>CauHoi</b>.</li>
            <li>Loại câu hỏi: SINGLE_CHOICE, MULTIPLE_SELECT hoặc FILL_BLANK.</li>
            <li>Đáp án đúng nhập số 1–4; nhiều đáp án cách nhau bằng dấu phẩy.</li>
            <li>Đáp án điền khuyết cách nhau bằng dấu <b>|</b>.</li>
            <li>Mức độ tư duy nhận L1–L5; tổng Quiz không vượt quá {MAX_QUESTIONS_PER_QUIZ} câu.</li>
            <li>Nếu một dòng sai, hệ thống không lưu bất kỳ dòng nào.</li>
          </ul>
          <Button type="button" size="sm" variant="outline" className="mt-3" disabled={downloading} onClick={() => void downloadTemplate()}>
            <Download className="h-4 w-4" />
            {downloading ? "Đang tải…" : "Tải file Excel mẫu"}
          </Button>
        </section>

        <section>
          <h4 className="font-bold">Xem trước dữ liệu mẫu</h4>
          <div className="mt-2 overflow-x-auto rounded-lg border">
            <table className="min-w-[850px] w-full text-left text-xs">
              <thead className="bg-[#C8102E] text-white">
                <tr>{["Loại", "Nội dung", "Lựa chọn", "Đáp án", "Điểm", "Mức độ"].map((value) => <th key={value} className="p-2">{value}</th>)}</tr>
              </thead>
              <tbody className="divide-y">
                <tr><td className="p-2 font-semibold">SINGLE_CHOICE</td><td className="p-2">Thủ đô của Việt Nam là gì?</td><td className="p-2">4 lựa chọn</td><td className="p-2">1</td><td className="p-2">1</td><td className="p-2">L1</td></tr>
                <tr><td className="p-2 font-semibold">MULTIPLE_SELECT</td><td className="p-2">Chọn các số nguyên tố.</td><td className="p-2">4 lựa chọn</td><td className="p-2">1,2</td><td className="p-2">1.5</td><td className="p-2">L2</td></tr>
                <tr><td className="p-2 font-semibold">FILL_BLANK</td><td className="p-2">Công thức năng lượng là ____.</td><td className="p-2">Để trống</td><td className="p-2">$E=mc^2$|E=mc^2</td><td className="p-2">2</td><td className="p-2">L3</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <label className="flex cursor-pointer flex-col items-center rounded-lg border-2 border-dashed border-[#C8102E]/40 bg-[#FFF8E8] p-7 text-center">
          <FileSpreadsheet className="mb-2 h-8 w-8 text-[#C8102E]" />
          <b>{file ? file.name : "Chọn file Excel cần import"}</b>
          <span className="mt-1 text-xs text-[#6B7280]">.xlsx · tối đa 5 MB</span>
          <input
            aria-label="Chọn file Excel cần import"
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            className="hidden"
            disabled={saving}
            onChange={(event) => {
              const selected = event.target.files?.[0] ?? null;
              setFile(selected);
              setApiError(null);
              setLocalError(selected ? validateQuestionImportFile(selected) : null);
            }}
          />
        </label>

        {(localError || apiError) && (
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            <b>{apiError?.code ?? "EXCEL_FILE_INVALID"}</b>
            <p className="mt-1">{localError ?? apiError?.message}</p>
            {apiError?.traceId && <p className="mt-1 text-xs">Mã yêu cầu: {apiError.traceId}</p>}
            {errorGroups.length > 0 && (
              <div className="mt-3 max-h-56 space-y-2 overflow-y-auto rounded border border-red-200 bg-white p-3">
                {errorGroups.map((group) => (
                  <div key={group.location}>
                    <b>{group.location}</b>
                    <ul className="mt-1 list-inside list-disc">
                      {group.errors.map((detail, index) => (
                        <li key={`${detail.code}-${index}`}><span className="font-semibold">{detail.code}</span>: {detail.message}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <Button className="w-full" disabled={saving || !file || Boolean(localError)} onClick={() => void submit()}>
          <Upload className="h-4 w-4" />
          {saving ? "Đang kiểm tra và import…" : "Import câu hỏi"}
        </Button>
      </div>
    </Modal>
  );
}
