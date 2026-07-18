import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { FileText, UploadCloud, X, Zap } from "lucide-react";
import { toast } from "sonner";
import { bkquizApi, type Visibility } from "../../api/bkquiz";
import { Button, Card, Input } from "../components/ui";

export default function NewTopic() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("PRIVATE");
  const [files, setFiles] = useState<File[]>([]);
  const [pasteName, setPasteName] = useState("");
  const [pasteText, setPasteText] = useState("");
  const [saving, setSaving] = useState(false);
  const submit = async () => {
    if (!title.trim()) return toast.error("Vui lòng nhập tên chủ đề.");
    setSaving(true);
    try {
      const topic = await bkquizApi.createTopic({
        title: title.trim(),
        description: description.trim(),
        visibility,
      });
      const uploads = files.map((file) =>
        bkquizApi.uploadSource(topic.id, file),
      );
      if (pasteText.trim())
        uploads.push(
          bkquizApi
            .pasteSource(
              topic.id,
              pasteName.trim() || "Văn bản đã dán",
              pasteText.trim(),
            )
            .then((source) => ({ source, jobId: "" })),
        );
      const results = await Promise.allSettled(uploads);
      const failed = results.filter(
        (result) => result.status === "rejected",
      ).length;
      toast.success(
        failed
          ? `Đã tạo chủ đề; ${failed} nguồn tải lên chưa thành công.`
          : "Đã tạo chủ đề và gửi tài liệu xử lý.",
      );
      navigate(`/workspace/${topic.id}`);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Không thể tạo chủ đề.",
      );
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="min-h-screen bg-[#F7F7F8] p-4 text-[#111827] md:p-8">
      <Card className="mx-auto max-w-5xl overflow-hidden">
        <header className="flex items-center justify-between border-b p-5">
          <div className="flex items-center gap-3">
            <span className="rounded-md bg-[#C8102E] p-2 text-white">
              <Zap className="h-5 w-5" />
            </span>
            <div>
              <h1 className="font-black">Tạo chủ đề mới</h1>
              <p className="text-xs text-[#6B7280]">
                Thông tin và tài liệu sẽ được lưu vào BKQuiz.
              </p>
            </div>
          </div>
          <Link to="/dashboard">
            <X />
          </Link>
        </header>
        <main className="grid gap-6 p-5 md:grid-cols-2 md:p-8">
          <section className="space-y-5">
            <label className="block text-sm font-black">
              Tên chủ đề
              <Input
                className="mt-2"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
                autoFocus
              />
            </label>
            <label className="block text-sm font-black">
              Mô tả
              <textarea
                className="mt-2 min-h-32 w-full rounded-md border p-3 font-normal"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={5000}
              />
            </label>
            <label className="block text-sm font-black">
              Quyền riêng tư
              <select
                className="mt-2 h-10 w-full rounded-md border bg-white px-3"
                value={visibility}
                onChange={(e) => setVisibility(e.target.value as Visibility)}
              >
                <option value="PRIVATE">Riêng tư</option>
                <option value="PUBLIC">Công khai</option>
              </select>
            </label>
          </section>
          <section className="space-y-5">
            <label className="flex min-h-36 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed bg-[#FFF8E8] p-5 text-center">
              <UploadCloud className="mb-3 h-8 w-8 text-[#C8102E]" />
              <b>Chọn tài liệu</b>
              <span className="mt-1 text-xs text-[#6B7280]">
                PDF, DOCX, PPTX, TXT · tối đa 50 MB
              </span>
              <input
                className="hidden"
                type="file"
                multiple
                accept=".pdf,.docx,.pptx,.txt"
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              />
            </label>
            {files.length > 0 && (
              <Card className="p-3">
                {files.map((file) => (
                  <div
                    key={`${file.name}-${file.size}`}
                    className="flex items-center gap-2 py-1 text-sm"
                  >
                    <FileText className="h-4 w-4" />
                    <span className="min-w-0 flex-1 truncate">{file.name}</span>
                    <button
                      onClick={() =>
                        setFiles((current) =>
                          current.filter((item) => item !== file),
                        )
                      }
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </Card>
            )}
            <div>
              <h2 className="mb-2 text-sm font-black">Hoặc dán văn bản</h2>
              <Input
                placeholder="Tên tài liệu"
                value={pasteName}
                onChange={(e) => setPasteName(e.target.value)}
              />
              <textarea
                className="mt-2 min-h-32 w-full rounded-md border p-3 text-sm"
                placeholder="Ít nhất 100 ký tự..."
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
              />
            </div>
          </section>
        </main>
        <footer className="flex justify-end gap-2 border-t p-5">
          <Link to="/dashboard">
            <Button variant="outline">Hủy</Button>
          </Link>
          <Button
            disabled={
              saving || (Boolean(pasteText) && pasteText.trim().length < 100)
            }
            onClick={submit}
          >
            {saving ? "Đang tạo..." : "Tạo và mở Workspace"}
          </Button>
        </footer>
      </Card>
    </div>
  );
}
