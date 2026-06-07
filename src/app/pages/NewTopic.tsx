import { useState } from "react";
import { Link, useNavigate } from "react-router";
import {
  AlertCircle,
  CheckCircle2,
  Clipboard,
  FileText,
  HardDrive,
  Link as LinkIcon,
  Loader2,
  Plus,
  Trash2,
  UploadCloud,
  X,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { Button, Card, Checkbox, Input } from "../components/ui";
import { sourceFiles } from "../data/mock";

type UploadState = "idle" | "uploading" | "parsed" | "error";

export default function NewTopic() {
  const navigate = useNavigate();
  const [files, setFiles] = useState(sourceFiles);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [topicName, setTopicName] = useState("Kỹ thuật truyền thông - GK 2026");

  const addFile = () => {
    setUploadState("uploading");
    toast.loading("Đang tải file lên...", { id: "upload" });
    setTimeout(() => {
      const nextFile = {
        id: Date.now(),
        name: "De_cuong_on_tap_GK.pdf",
        size: "1.8 MB",
        type: "PDF",
        selected: true,
      };
      setFiles((current) => [nextFile, ...current]);
      setUploadState("parsed");
      toast.success("Đã phân tích file thành công.", { id: "upload" });
    }, 900);
  };

  const failUpload = () => {
    setUploadState("error");
    toast.error("File không được hỗ trợ trong bản demo.");
  };

  const continueFlow = () => {
    if (!topicName.trim()) {
      toast.error("Vui lòng nhập tên chủ đề.");
      return;
    }
    toast.success("Chủ đề đã sẵn sàng. Chuyển sang Workspace.");
    navigate("/workspace/1");
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#2F2A25]/80 p-4 font-sans text-[#111827] md:p-8">
      <Card className="flex h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-lg bg-white shadow-2xl">
        <header className="flex shrink-0 items-center justify-between border-b border-[#E5E7EB] px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-md bg-[#C8102E] text-white">
              <Zap className="h-5 w-5 fill-current" />
            </span>
            <div>
              <h1 className="font-black">Tạo chủ đề mới</h1>
              <p className="text-xs text-[#6B7280]">Import tài liệu để BKQuiz sinh câu hỏi.</p>
            </div>
          </div>
          <Link to="/dashboard">
            <button className="rounded-md p-2 text-[#6B7280] hover:bg-[#F7F7F8]" aria-label="Đóng">
              <X className="h-5 w-5" />
            </button>
          </Link>
        </header>

        <div className="grid min-h-0 flex-1 md:grid-cols-[300px_1fr]">
          <aside className="hidden min-h-0 border-r border-[#E5E7EB] bg-[#F7F7F8] md:flex md:flex-col">
            <div className="border-b border-[#E5E7EB] p-4">
              <h2 className="font-black">Nguồn</h2>
              <p className="mt-1 text-xs text-[#6B7280]">{files.length} file đã thêm</p>
            </div>
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
              {files.map((file) => (
                <Card key={file.id} className="flex gap-3 p-3">
                  <Checkbox
                    checked={file.selected}
                    onChange={() =>
                      setFiles((current) =>
                        current.map((item) => (item.id === file.id ? { ...item, selected: !item.selected } : item)),
                      )
                    }
                    className="mt-1"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-bold">{file.name}</p>
                    <div className="mt-1 flex items-center gap-2">
                      <span className="rounded bg-[#FDE7EA] px-1.5 py-0.5 text-[10px] font-black text-[#C8102E]">{file.type}</span>
                      <span className="text-xs text-[#6B7280]">{file.size}</span>
                    </div>
                  </div>
                  <button
                    className="self-start rounded p-1 text-[#9CA3AF] hover:bg-[#FDE7EA] hover:text-[#DC2626]"
                    onClick={() => {
                      setFiles((current) => current.filter((item) => item.id !== file.id));
                      toast.info("Đã bỏ file khỏi danh sách.");
                    }}
                    aria-label="Xóa file"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </Card>
              ))}
            </div>
          </aside>

          <main className="min-h-0 overflow-y-auto bg-white p-5 md:p-8">
            <div className="mx-auto max-w-3xl space-y-7">
              <div>
                <label className="mb-2 block text-sm font-black">Tên chủ đề</label>
                <Input
                  className="h-12 text-base"
                  value={topicName}
                  onChange={(event) => setTopicName(event.target.value)}
                  placeholder="VD: Kỹ thuật truyền thông - GK 2026"
                  autoFocus
                />
              </div>

              <div>
                <label className="mb-3 block text-sm font-black">Thêm nguồn tài liệu</label>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  {[
                    [UploadCloud, "Tải tệp lên", true],
                    [Clipboard, "Dán văn bản", false],
                    [HardDrive, "Google Drive", false],
                    [LinkIcon, "Nhập URL", false],
                  ].map(([Icon, label, active]) => {
                    const IconComponent = Icon as typeof UploadCloud;
                    return (
                      <button
                        key={String(label)}
                        className={`flex min-h-20 flex-col items-center justify-center gap-2 rounded-lg border p-3 text-xs font-black transition ${
                          active ? "border-[#C8102E] bg-[#FDE7EA] text-[#C8102E]" : "border-[#E5E7EB] bg-white text-[#6B7280] hover:bg-[#F7F7F8]"
                        }`}
                        onClick={() => (active ? addFile() : toast.info(`${label} đang ở chế độ demo.`))}
                      >
                        <IconComponent className="h-5 w-5" />
                        {String(label)}
                      </button>
                    );
                  })}
                </div>
              </div>

              <button
                type="button"
                onClick={addFile}
                onDoubleClick={failUpload}
                className="group flex min-h-[260px] w-full flex-col items-center justify-center rounded-lg border-2 border-dashed border-[#D1D5DB] bg-[#FFF8E8] px-6 text-center transition hover:border-[#C8102E] hover:bg-[#FFF4D9]"
              >
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-white text-[#C8102E] shadow-sm transition group-hover:scale-105">
                  {uploadState === "uploading" ? <Loader2 className="h-8 w-8 animate-spin" /> : <UploadCloud className="h-8 w-8" />}
                </div>
                <h3 className="text-xl font-black">Kéo thả tệp của bạn vào đây</h3>
                <p className="mt-2 max-w-md text-sm leading-6 text-[#6B7280]">
                  PDF, PPT, DOCX, hình ảnh, âm thanh. Nhấn một lần để mô phỏng upload thành công, nhấn đúp để mô phỏng lỗi.
                </p>
                <div className="mt-5 flex flex-wrap justify-center gap-2 text-xs font-bold">
                  <span className="rounded bg-white px-2 py-1 text-[#6B7280]">Tối đa 50MB/file</span>
                  <span className="rounded bg-white px-2 py-1 text-[#6B7280]">Hỗ trợ tài liệu môn học</span>
                </div>
              </button>

              {uploadState === "uploading" && (
                <Card className="p-4">
                  <div className="mb-2 flex items-center justify-between text-sm font-bold">
                    <span>Đang upload và phân tích...</span>
                    <span className="text-[#C8102E]">68%</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-[#F3F4F6]">
                    <div className="h-full w-2/3 rounded-full bg-[#C8102E]" />
                  </div>
                </Card>
              )}

              {uploadState === "parsed" && (
                <Card className="flex gap-3 border-[#BBF7D0] bg-[#F0FDF4] p-4">
                  <CheckCircle2 className="h-5 w-5 shrink-0 text-[#16A34A]" />
                  <div>
                    <h4 className="font-black text-[#166534]">Đã phân tích xong</h4>
                    <p className="mt-1 text-sm text-[#166534]/80">BKQuiz tìm thấy 38 khái niệm trọng tâm và 12 công thức có thể tạo câu hỏi.</p>
                  </div>
                </Card>
              )}

              {uploadState === "error" && (
                <Card className="flex gap-3 border-[#FECACA] bg-[#FEF2F2] p-4">
                  <AlertCircle className="h-5 w-5 shrink-0 text-[#DC2626]" />
                  <div>
                    <h4 className="font-black text-[#991B1B]">File không hỗ trợ</h4>
                    <p className="mt-1 text-sm text-[#991B1B]/80">Hãy thử định dạng PDF, PPT, DOCX hoặc ảnh rõ chữ.</p>
                  </div>
                </Card>
              )}

              <div className="grid gap-3 md:hidden">
                <h3 className="font-black">File đã thêm</h3>
                {files.map((file) => (
                  <Card key={file.id} className="flex items-center gap-3 p-3">
                    <FileText className="h-5 w-5 text-[#C8102E]" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-bold">{file.name}</p>
                      <p className="text-xs text-[#6B7280]">{file.type} - {file.size}</p>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          </main>
        </div>

        <footer className="flex shrink-0 flex-col-reverse gap-3 border-t border-[#E5E7EB] bg-white p-4 sm:flex-row sm:justify-end">
          <Link to="/dashboard">
            <Button variant="outline" className="w-full sm:w-auto">Hủy</Button>
          </Link>
          <Button className="w-full sm:w-auto" onClick={continueFlow}>
            <Plus className="h-4 w-4" />
            Tiếp tục tạo quiz
          </Button>
        </footer>
      </Card>
    </div>
  );
}
