import { useState } from "react";
import { toast } from "sonner";
import { ApiRequestError } from "../../api/client";
import { bkquizApi, type Quiz, type Visibility } from "../../api/bkquiz";
import { Button, Input, Modal } from "../components/ui";

export function BlankQuizModal({
  topicId,
  onClose,
  onCreated,
}: {
  topicId: string;
  onClose: () => void;
  onCreated: (quiz: Quiz) => void | Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [durationMinutes, setDurationMinutes] = useState(45);
  const [visibility, setVisibility] = useState<Visibility>("PRIVATE");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiRequestError | null>(null);

  const submit = async () => {
    if (!title.trim()) {
      toast.error("Nhập tên quiz.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const quiz = await bkquizApi.createQuiz({
        topicId,
        title: title.trim(),
        ...(description.trim() ? { description: description.trim() } : {}),
        cognitiveMode: "BALANCED",
        durationMinutes,
        visibility,
      });
      await onCreated(quiz);
      toast.success("Đã tạo quiz trống.");
    } catch (value) {
      if (value instanceof ApiRequestError) setError(value);
      else toast.error(value instanceof Error ? value.message : "Không thể tạo quiz.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Tạo quiz trống" onClose={onClose} className="max-w-xl">
      <div className="space-y-4 p-5">
        <p className="rounded-lg bg-blue-50 p-3 text-sm text-blue-900">
          Quiz mới chưa có câu hỏi. Sau khi tạo, bạn có thể thêm câu thủ công,
          import Excel hoặc sinh thêm bằng AI.
        </p>
        <label className="block text-sm font-bold">
          Tên quiz
          <Input value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>
        <label className="block text-sm font-bold">
          Mô tả
          <textarea
            className="mt-1 min-h-24 w-full rounded-md border bg-white p-3 font-normal"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm font-bold">
            Thời lượng
            <Input
              type="number"
              min={1}
              max={300}
              value={durationMinutes}
              onChange={(event) => setDurationMinutes(Number(event.target.value))}
            />
          </label>
          <label className="text-sm font-bold">
            Hiển thị
            <select
              className="mt-1 h-10 w-full rounded-md border bg-white px-3 font-normal"
              value={visibility}
              onChange={(event) => setVisibility(event.target.value as Visibility)}
            >
              <option value="PRIVATE">Riêng tư</option>
              <option value="PUBLIC">Công khai</option>
            </select>
          </label>
        </div>
        {error && (
          <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            <b>{error.message}</b>
            {error.code && <p>Mã lỗi: {error.code}</p>}
            {error.traceId && <p>Mã yêu cầu: {error.traceId}</p>}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="outline" disabled={saving} onClick={onClose}>Hủy</Button>
          <Button disabled={saving || durationMinutes < 1 || durationMinutes > 300} onClick={() => void submit()}>
            {saving ? "Đang tạo..." : "Tạo quiz trống"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
