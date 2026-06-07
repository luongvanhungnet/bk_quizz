import { useState } from "react";
import { Link, useNavigate } from "react-router";
import {
  BarChart3,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  Download,
  Edit3,
  FileQuestion,
  FileText,
  FileUp,
  Globe2,
  Link as LinkIcon,
  Loader2,
  Lock,
  MessageCircle,
  Plus,
  Play,
  Send,
  Settings,
  Trash2,
  UploadCloud,
  X,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, Card, Checkbox, Input, Modal } from "../components/ui";
import { questions, quizzes, sourceFiles } from "../data/mock";

type ModalName = "addSource" | "practice" | "export" | "stats" | "delete" | "settings" | null;
type Step = "config" | "loading" | "preview";

export default function Workspace() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("config");
  const [activeModal, setActiveModal] = useState<ModalName>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [isPublic, setIsPublic] = useState(false);
  const [sources, setSources] = useState(sourceFiles);
  const [currentQuizId, setCurrentQuizId] = useState(quizzes[0].id);
  const [takeQuiz, setTakeQuiz] = useState<(typeof quizzes)[number] | null>(null);
  const [expandedQuestion, setExpandedQuestion] = useState(1);
  const [exportFormat, setExportFormat] = useState("pdf");

  const currentQuiz = quizzes.find((quiz) => quiz.id === currentQuizId) ?? quizzes[0];

  const generateQuiz = () => {
    setStep("loading");
    toast.loading("AI đang phân tích tài liệu...", { id: "generate" });
    setTimeout(() => {
      setStep("preview");
      toast.success("Đã tạo quiz mới với 30 câu hỏi.", { id: "generate" });
    }, 1200);
  };

  const toggleSource = (id: number) => {
    setSources((current) => current.map((item) => (item.id === id ? { ...item, selected: !item.selected } : item)));
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#F7F7F8] font-sans text-[#111827]">
      <header className="z-20 flex h-14 shrink-0 items-center justify-between border-b border-[#E5E7EB] bg-white px-4">
        <Link to="/dashboard" className="flex items-center gap-2 text-lg font-black text-[#C8102E]">
          <Zap className="h-5 w-5 fill-current" />
          BKQuiz
        </Link>
        <button className="hidden items-center gap-2 rounded-md border border-[#E5E7EB] bg-[#F7F7F8] px-3 py-1.5 text-sm font-bold hover:bg-white md:flex">
          <FileText className="h-4 w-4 text-[#6B7280]" />
          Kỹ thuật truyền thông - GK
          <ChevronDown className="h-4 w-4 text-[#6B7280]" />
        </button>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => setActiveModal("export")}>
            <Download className="h-4 w-4" />
            Xuất file
          </Button>
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#C8102E] text-sm font-black text-white">SV</div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-72 shrink-0 flex-col border-r border-[#E5E7EB] bg-white md:flex">
          <div className="border-b border-[#E5E7EB] p-4">
            <Button className="w-full" onClick={() => setStep("config")}>
              <Plus className="h-4 w-4" />
              Tạo quiz mới
            </Button>
          </div>

          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-4">
            <section>
              <div className="mb-3 flex items-center justify-between text-xs font-black uppercase text-[#6B7280]">
                Nguồn tài liệu
                <ChevronDown className="h-4 w-4" />
              </div>
              <div className="space-y-2">
                {sources.map((file) => (
                  <label key={file.id} className="flex cursor-pointer items-center gap-2 rounded-md p-1.5 text-sm font-semibold hover:bg-[#F7F7F8]">
                    <Checkbox checked={file.selected} onChange={() => toggleSource(file.id)} />
                    <span className="min-w-0 flex-1 truncate">{file.name}</span>
                  </label>
                ))}
                <button
                  className="flex items-center gap-1 rounded-md px-1.5 py-1 text-sm font-black text-[#C8102E] hover:bg-[#FDE7EA]"
                  onClick={() => setActiveModal("addSource")}
                >
                  <Plus className="h-4 w-4" />
                  Thêm nguồn
                </button>
              </div>
            </section>

            <section>
              <div className="mb-3 flex items-center justify-between text-xs font-black uppercase text-[#6B7280]">
                Quiz đã tạo ({quizzes.length})
                <ChevronDown className="h-4 w-4" />
              </div>
              <div className="space-y-2">
                {quizzes.map((quiz) => {
                  const active = quiz.id === currentQuizId;
                  return (
                    <Card
                      key={quiz.id}
                      className={`group relative cursor-pointer p-3 transition ${active ? "border-[#F4A7B3] bg-[#FFF1F3]" : "hover:border-[#C8102E]/40"}`}
                      onClick={() => {
                        setCurrentQuizId(quiz.id);
                        setStep("preview");
                      }}
                    >
                      <div className="flex gap-3">
                        <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${active ? "bg-white text-[#C8102E]" : "bg-[#F7F7F8] text-[#6B7280]"}`}>
                          <FileQuestion className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className={`truncate text-sm font-black ${active ? "text-[#C8102E]" : ""}`}>{quiz.title}</p>
                          <p className="mt-0.5 text-xs text-[#6B7280]">{quiz.count} câu - {quiz.createdAt}</p>
                        </div>
                      </div>
                      <div className="mt-3 grid grid-cols-3 gap-1 opacity-100 md:opacity-0 md:group-hover:opacity-100">
                        <button
                          className="rounded border border-[#E5E7EB] bg-white p-1.5 text-[#16A34A] hover:bg-[#F0FDF4]"
                          onClick={(event) => {
                            event.stopPropagation();
                            setTakeQuiz(quiz);
                          }}
                          title="Làm thử"
                        >
                          <Play className="mx-auto h-3.5 w-3.5 fill-current" />
                        </button>
                        <button
                          className="rounded border border-[#E5E7EB] bg-white p-1.5 text-[#6B7280] hover:bg-[#F7F7F8]"
                          onClick={(event) => {
                            event.stopPropagation();
                            setActiveModal("export");
                          }}
                          title="Xuất"
                        >
                          <Download className="mx-auto h-3.5 w-3.5" />
                        </button>
                        <button
                          className="rounded border border-[#E5E7EB] bg-white p-1.5 text-[#DC2626] hover:bg-[#FDE7EA]"
                          onClick={(event) => {
                            event.stopPropagation();
                            setActiveModal("delete");
                          }}
                          title="Xóa"
                        >
                          <Trash2 className="mx-auto h-3.5 w-3.5" />
                        </button>
                      </div>
                    </Card>
                  );
                })}
              </div>
            </section>
          </div>
        </aside>

        <main className="min-w-0 flex-1 overflow-y-auto p-4 md:p-8">
          <div className="mx-auto max-w-3xl space-y-6">
            <div className="flex items-center gap-3 border-b border-[#E5E7EB] pb-5 text-sm font-black">
              {[
                ["config", "Cấu hình"],
                ["loading", "Sinh đề"],
                ["preview", "Biên tập"],
              ].map(([id, label], index) => {
                const active = id === step || (step === "preview" && index < 2);
                return (
                  <div key={id} className="flex items-center gap-3">
                    <span className={`flex h-7 w-7 items-center justify-center rounded-full text-xs ${active ? "bg-[#C8102E] text-white" : "bg-[#E5E7EB] text-[#6B7280]"}`}>
                      {index + 1}
                    </span>
                    <span className={active ? "text-[#111827]" : "text-[#6B7280]"}>{label}</span>
                    {index < 2 && <span className="hidden h-px w-12 bg-[#E5E7EB] sm:block" />}
                  </div>
                );
              })}
            </div>

            {step === "config" && (
              <Card className="p-5 md:p-8">
                <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                  <div>
                    <h1 className="text-2xl font-black">Tạo quiz</h1>
                    <p className="mt-1 text-sm text-[#6B7280]">Thiết lập thông số để AI sinh câu hỏi từ tài liệu đã chọn.</p>
                  </div>
                  <div className="flex rounded-lg border border-[#E5E7EB] bg-[#F7F7F8] p-1">
                    <button
                      className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-black ${!isPublic ? "bg-white text-[#111827] shadow-sm" : "text-[#6B7280]"}`}
                      onClick={() => setIsPublic(false)}
                    >
                      <Lock className="h-3.5 w-3.5" />
                      Private
                    </button>
                    <button
                      className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-black ${isPublic ? "bg-white text-[#C8102E] shadow-sm" : "text-[#6B7280]"}`}
                      onClick={() => setIsPublic(true)}
                    >
                      <Globe2 className="h-3.5 w-3.5" />
                      Public
                    </button>
                  </div>
                </div>

                <div className="space-y-6">
                  <div>
                    <label className="mb-2 block text-sm font-black">Phạm vi tài liệu</label>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {sources.map((file) => (
                        <label key={file.id} className="flex cursor-pointer items-center gap-2 rounded-md border border-[#E5E7EB] p-3 text-sm font-semibold">
                          <Checkbox checked={file.selected} onChange={() => toggleSource(file.id)} />
                          <span className="truncate">{file.name}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="grid gap-5 md:grid-cols-2">
                    <div>
                      <label className="mb-2 block text-sm font-black">Độ khó</label>
                      <div className="grid grid-cols-3 rounded-lg border border-[#E5E7EB] bg-[#F7F7F8] p-1">
                        {["Dễ", "Trung bình", "Khó"].map((level) => (
                          <button key={level} className={`rounded-md py-2 text-sm font-bold ${level === "Trung bình" ? "bg-white text-[#C8102E] shadow-sm" : "text-[#6B7280]"}`}>
                            {level}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div>
                      <label className="mb-2 block text-sm font-black">Thời lượng làm bài (phút)</label>
                      <Input type="number" defaultValue={45} className="h-11 text-center text-base font-bold" />
                    </div>
                  </div>

                  <div className="border-t border-[#E5E7EB] pt-5">
                    <div className="mb-4 flex items-center justify-between">
                      <h2 className="font-black">Số câu theo loại</h2>
                      <span className="text-sm font-black text-[#C8102E]">Tổng: 30 câu</span>
                    </div>
                    <div className="space-y-3">
                      {[
                        ["Trắc nghiệm 1 đáp án", 20],
                        ["Trắc nghiệm nhiều đáp án", 5],
                        ["Điền vào chỗ trống", 3],
                        ["Tự luận ngắn", 2],
                      ].map(([label, value]) => (
                        <div key={String(label)} className="flex items-center justify-between gap-4">
                          <span className="text-sm font-semibold">{label}</span>
                          <Input type="number" defaultValue={Number(value)} className="w-20 text-center font-bold" />
                        </div>
                      ))}
                    </div>
                  </div>

                  <Card className="flex gap-3 border-[#BBF7D0] bg-[#F0FDF4] p-4">
                    <BrainCircuit className="mt-0.5 h-5 w-5 shrink-0 text-[#16A34A]" />
                    <div>
                      <h3 className="font-black text-[#166534]">Tính năng nâng cao</h3>
                      <label className="mt-2 flex cursor-pointer items-center gap-2 text-sm font-semibold text-[#166534]">
                        <Checkbox defaultChecked />
                        Ưu tiên sinh câu hỏi tư duy / vận dụng cao
                      </label>
                    </div>
                  </Card>

                  <Button size="lg" className="w-full text-lg" onClick={generateQuiz}>
                    <Zap className="h-5 w-5 fill-current" />
                    Generate Quiz
                  </Button>
                </div>
              </Card>
            )}

            {step === "loading" && (
              <Card className="flex min-h-[430px] flex-col items-center justify-center p-10 text-center">
                <Loader2 className="mb-6 h-14 w-14 animate-spin text-[#C8102E]" />
                <h2 className="text-2xl font-black">Đang phân tích tài liệu...</h2>
                <p className="mt-2 max-w-md text-sm leading-6 text-[#6B7280]">AI đang trích xuất khái niệm trọng tâm, công thức và ví dụ từ 2 file nguồn.</p>
                <div className="mt-8 h-2 w-full max-w-sm overflow-hidden rounded-full bg-[#F3F4F6]">
                  <div className="h-full w-2/3 animate-pulse rounded-full bg-[#C8102E]" />
                </div>
              </Card>
            )}

            {step === "preview" && (
              <div className="space-y-4">
                <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
                  <div>
                    <div className="flex items-center gap-2">
                      <h1 className="text-2xl font-black">{currentQuiz.title}</h1>
                      <Badge className="bg-[#F7F7F8] text-[#6B7280]">{isPublic ? "Public" : "Private"}</Badge>
                    </div>
                    <p className="mt-1 text-sm text-[#6B7280]">{currentQuiz.count} câu hỏi - {currentQuiz.duration} phút - Độ khó: {currentQuiz.difficulty}</p>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" onClick={() => setActiveModal("export")}>
                      <Download className="h-4 w-4" />
                      Xuất quiz
                    </Button>
                    <Button onClick={() => setTakeQuiz(currentQuiz)}>
                      <Play className="h-4 w-4 fill-current" />
                      Làm thử
                    </Button>
                  </div>
                </div>

                {questions.slice(0, 5).map((question) => {
                  const open = expandedQuestion === question.id;
                  return (
                    <Card key={question.id} className="overflow-hidden">
                      <button
                        className="flex w-full items-start justify-between gap-4 p-4 text-left hover:bg-[#F9FAFB]"
                        onClick={() => setExpandedQuestion(open ? 0 : question.id)}
                      >
                        <div className="flex gap-3">
                          <span className="font-black text-[#C8102E]">Q{question.id}.</span>
                          <div>
                            <p className="font-bold">{question.text}</p>
                            <Badge className="mt-2 bg-[#F7F7F8] text-[#6B7280]">{question.type === "single" ? "Trắc nghiệm" : question.type === "multiple" ? "Nhiều đáp án" : "Điền khuyết"}</Badge>
                          </div>
                        </div>
                        <ChevronDown className={`h-5 w-5 shrink-0 text-[#9CA3AF] transition ${open ? "rotate-180" : ""}`} />
                      </button>
                      {open && (
                        <div className="space-y-3 border-t border-[#E5E7EB] bg-[#F9FAFB] p-4">
                          <div className="rounded-md border border-[#BBF7D0] bg-[#F0FDF4] p-3 text-sm">
                            <b className="text-[#166534]">Đáp án:</b>{" "}
                            {Array.isArray(question.correct) ? question.correct.join(", ") : question.correct}
                          </div>
                          <div className="rounded-md border border-[#E5E7EB] bg-white p-3 text-sm leading-6 text-[#4B5563]">
                            <b>Giải thích:</b> {question.explanation}
                          </div>
                          <div className="flex justify-end gap-2">
                            <Button size="sm" variant="ghost" onClick={() => toast.info("Mở chế độ sửa câu hỏi demo.")}>
                              <Edit3 className="h-4 w-4" />
                              Sửa
                            </Button>
                            <Button size="sm" variant="ghost" className="text-[#DC2626]" onClick={() => toast.error("Đã mô phỏng xóa câu hỏi.")}>
                              <Trash2 className="h-4 w-4" />
                              Xóa
                            </Button>
                          </div>
                        </div>
                      )}
                    </Card>
                  );
                })}

                <Button variant="outline" className="w-full border-dashed bg-white py-6" onClick={() => toast.success("Đã thêm câu hỏi mới vào bản nháp.")}>
                  <Plus className="h-4 w-4" />
                  Thêm câu hỏi mới
                </Button>
              </div>
            )}
          </div>
        </main>

        <aside className="hidden w-64 shrink-0 border-l border-[#E5E7EB] bg-white lg:flex lg:flex-col">
          <div className="border-b border-[#E5E7EB] p-4">
            <h2 className="font-black">Studio Công cụ</h2>
          </div>
          <div className="flex-1 space-y-2 p-4">
            {[
              [Zap, "Tạo quiz", () => setStep("config"), true],
              [Play, "Thi thử", () => setActiveModal("practice"), false],
              [Download, "Xuất quiz", () => setActiveModal("export"), false],
              [BarChart3, "Thống kê", () => setActiveModal("stats"), false],
              [Settings, "Cài đặt chủ đề", () => setActiveModal("settings"), false],
            ].map(([Icon, label, action, primary]) => {
              const IconComponent = Icon as typeof Zap;
              return (
                <button
                  key={String(label)}
                  onClick={action as () => void}
                  className={`flex w-full items-center gap-3 rounded-md px-3 py-3 text-sm font-black transition ${
                    primary ? "bg-[#FDE7EA] text-[#C8102E]" : "text-[#6B7280] hover:bg-[#F7F7F8] hover:text-[#111827]"
                  }`}
                >
                  <IconComponent className="h-5 w-5" />
                  {String(label)}
                </button>
              );
            })}

            <div className="mt-8 border-t border-[#E5E7EB] pt-6">
              <p className="mb-4 text-xs font-black uppercase text-[#6B7280]">Tổng quan</p>
              <div className="space-y-4">
                <div>
                  <div className="text-3xl font-black">{quizzes.length}</div>
                  <div className="text-xs text-[#6B7280]">Quiz đã tạo</div>
                </div>
                <div>
                  <div className="text-3xl font-black">128</div>
                  <div className="text-xs text-[#6B7280]">Tổng câu hỏi</div>
                </div>
                <div>
                  <div className="text-3xl font-black text-[#16A34A]">8.2/10</div>
                  <div className="text-xs text-[#6B7280]">Điểm trung bình</div>
                </div>
              </div>
            </div>
          </div>
        </aside>
      </div>

      <div className="fixed bottom-6 right-6 z-40 lg:right-[18rem]">
        {chatOpen && (
          <Card className="absolute bottom-16 right-0 flex h-[420px] w-[330px] flex-col overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between bg-[#C8102E] px-4 py-3 text-white">
              <div className="flex items-center gap-2 text-sm font-black">
                <Bot className="h-5 w-5" />
                Hỏi AI về tài liệu
              </div>
              <button onClick={() => setChatOpen(false)} className="rounded p-1 hover:bg-white/10">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 space-y-3 overflow-y-auto bg-[#F9FAFB] p-4 text-sm">
              <div className="max-w-[85%] rounded-lg rounded-tl-sm border border-[#E5E7EB] bg-white p-3 shadow-sm">
                Mình đã đọc các file nguồn. Bạn muốn giải thích câu nào trong quiz này?
              </div>
              <div className="ml-auto max-w-[85%] rounded-lg rounded-tr-sm bg-[#FDE7EA] p-3 font-semibold text-[#C8102E]">
                Vì sao TCP thuộc tầng giao vận?
              </div>
            </div>
            <div className="border-t border-[#E5E7EB] bg-white p-3">
              <div className="relative">
                <Input placeholder="Nhập câu hỏi..." className="pr-10" />
                <button className="absolute right-2 top-1/2 -translate-y-1/2 rounded bg-[#FDE7EA] p-1.5 text-[#C8102E]" onClick={() => toast.info("AI chat đang ở chế độ demo.")}>
                  <Send className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </Card>
        )}
        <button
          onClick={() => setChatOpen((value) => !value)}
          className="flex h-14 w-14 items-center justify-center rounded-full bg-[#C8102E] text-white shadow-xl transition hover:scale-105 hover:bg-[#A50F24]"
          title="Hỏi AI về tài liệu/câu hỏi"
        >
          <MessageCircle className="h-7 w-7" />
        </button>
      </div>

      {activeModal === "addSource" && (
        <Modal title="Thêm tài liệu tham khảo" onClose={() => setActiveModal(null)}>
          <div className="space-y-5 p-5">
            <button
              className="flex w-full flex-col items-center justify-center rounded-lg border-2 border-dashed border-[#D1D5DB] p-8 text-center hover:border-[#C8102E] hover:bg-[#FFF8E8]"
              onClick={() => {
                setSources((current) => [{ id: Date.now(), name: "Tai_lieu_moi.pdf", size: "1.2 MB", type: "PDF", selected: true }, ...current]);
                toast.success("Đã thêm nguồn tài liệu mới.");
                setActiveModal(null);
              }}
            >
              <FileUp className="mb-3 h-8 w-8 text-[#C8102E]" />
              <b>Tải file lên</b>
              <span className="mt-1 text-sm text-[#6B7280]">PDF, DOCX, PPT, ảnh rõ chữ</span>
            </button>
            <div className="flex gap-2">
              <Input className="pl-9" placeholder="Nhập đường dẫn tài liệu..." />
              <LinkIcon className="pointer-events-none absolute h-4 w-4" />
              <Button onClick={() => toast.info("URL import đang ở chế độ demo.")}>Thêm URL</Button>
            </div>
          </div>
        </Modal>
      )}

      {activeModal === "practice" && (
        <Modal title="Chọn quiz thi thử" onClose={() => setActiveModal(null)} className="max-w-xl">
          <div className="space-y-3 bg-[#F9FAFB] p-5">
            {quizzes.map((quiz) => (
              <Card key={quiz.id} className="flex items-center justify-between gap-3 p-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-[#FDE7EA] text-[#C8102E]">
                    <FileQuestion className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="font-black">{quiz.title}</h3>
                    <p className="text-xs text-[#6B7280]">{quiz.count} câu - {quiz.duration} phút</p>
                  </div>
                </div>
                <Button size="sm" onClick={() => setTakeQuiz(quiz)}>Bắt đầu</Button>
              </Card>
            ))}
          </div>
        </Modal>
      )}

      {activeModal === "export" && (
        <Modal title="Xuất Quiz" onClose={() => setActiveModal(null)}>
          <div className="space-y-5 p-5">
            <div>
              <label className="mb-2 block text-sm font-black">Chọn định dạng file</label>
              <div className="grid grid-cols-3 gap-2">
                {["pdf", "docx", "csv"].map((format) => (
                  <button
                    key={format}
                    className={`rounded-md border px-3 py-2 text-sm font-black uppercase ${exportFormat === format ? "border-[#C8102E] bg-[#FDE7EA] text-[#C8102E]" : "border-[#E5E7EB] text-[#6B7280]"}`}
                    onClick={() => setExportFormat(format)}
                  >
                    {format}
                  </button>
                ))}
              </div>
            </div>
            <Button
              className="w-full"
              onClick={() => {
                toast.success(`Đã xuất ${currentQuiz.title} dạng ${exportFormat.toUpperCase()}.`);
                setActiveModal(null);
              }}
            >
              <Download className="h-4 w-4" />
              Tải xuống
            </Button>
          </div>
        </Modal>
      )}

      {activeModal === "stats" && (
        <Modal title="Thống kê chủ đề" onClose={() => setActiveModal(null)} className="max-w-2xl">
          <div className="space-y-5 bg-[#F9FAFB] p-5">
            <div className="grid gap-3 sm:grid-cols-4">
              {[
                ["Quiz", quizzes.length],
                ["Câu hỏi", 128],
                ["Lượt thi", 32],
                ["Điểm TB", "8.2/10"],
              ].map(([label, value]) => (
                <Card key={String(label)} className="p-4">
                  <div className="text-2xl font-black">{value}</div>
                  <div className="text-xs font-semibold text-[#6B7280]">{label}</div>
                </Card>
              ))}
            </div>
            <Card className="p-5">
              <h3 className="mb-4 font-black">Điểm trung bình theo quiz</h3>
              {quizzes.map((quiz, index) => (
                <div key={quiz.id} className="mb-4 last:mb-0">
                  <div className="mb-1 flex justify-between text-sm font-bold">
                    <span>{quiz.title}</span>
                    <span>{[8.7, 7.6, 8.1][index]}/10</span>
                  </div>
                  <div className="h-2 rounded-full bg-[#F3F4F6]">
                    <div className="h-full rounded-full bg-[#C8102E]" style={{ width: `${[87, 76, 81][index]}%` }} />
                  </div>
                </div>
              ))}
            </Card>
          </div>
        </Modal>
      )}

      {activeModal === "delete" && (
        <Modal title="Xóa quiz?" onClose={() => setActiveModal(null)} className="max-w-sm">
          <div className="p-5">
            <p className="text-sm leading-6 text-[#6B7280]">Bạn muốn xóa quiz đang chọn? Trong bản demo, thao tác này chỉ hiện thông báo.</p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setActiveModal(null)}>Hủy</Button>
              <Button
                variant="danger"
                onClick={() => {
                  toast.error("Đã mô phỏng xóa quiz.");
                  setActiveModal(null);
                }}
              >
                Xóa
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {activeModal === "settings" && (
        <Modal title="Cài đặt chủ đề" onClose={() => setActiveModal(null)}>
          <div className="space-y-3 p-5">
            <label className="block">
              <span className="mb-1.5 block text-sm font-black">Tên hiển thị</span>
              <Input defaultValue="Kỹ thuật truyền thông - GK" />
            </label>
            <label className="flex items-center gap-2 text-sm font-semibold">
              <Checkbox checked={isPublic} onChange={(event) => setIsPublic(event.currentTarget.checked)} />
              Chia sẻ chủ đề lên cộng đồng
            </label>
            <Button className="w-full" onClick={() => { toast.success("Đã lưu cài đặt chủ đề."); setActiveModal(null); }}>
              Lưu cài đặt
            </Button>
          </div>
        </Modal>
      )}

      {takeQuiz && (
        <Modal title="Bắt đầu làm bài?" onClose={() => setTakeQuiz(null)} className="max-w-sm">
          <div className="p-5">
            <p className="text-sm leading-6 text-[#6B7280]">
              Bạn sẵn sàng làm <b>{takeQuiz.title}</b>? Timer sẽ bắt đầu ngay khi xác nhận.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setTakeQuiz(null)}>Hủy</Button>
              <Button onClick={() => navigate(`/quiz/${takeQuiz.id}/take`)}>
                <Play className="h-4 w-4 fill-current" />
                Bắt đầu thi
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
