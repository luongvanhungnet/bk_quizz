import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import {
  Bot,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Flag,
  Menu,
  Save,
  ShieldAlert,
  Trophy,
  X,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, Card, Checkbox, Input, Modal } from "../components/ui";
import { questions } from "../data/mock";

type AnswerMap = Record<number, string | string[]>;
type Filter = "all" | "unanswered" | "marked";
type ResultTab = "overview" | "review" | "ai";

const totalQuestions = questions.length;

export default function QuizTaking() {
  const [submitted, setSubmitted] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [timeLeft, setTimeLeft] = useState(45 * 60);
  const [currentQ, setCurrentQ] = useState(1);
  const [answers, setAnswers] = useState<AnswerMap>({});
  const [marked, setMarked] = useState<number[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [resultTab, setResultTab] = useState<ResultTab>("overview");

  useEffect(() => {
    if (submitted) return;
    const timer = window.setInterval(() => {
      setTimeLeft((value) => {
        if (value <= 1) {
          window.clearInterval(timer);
          toast.warning("Hết giờ. BKQuiz tự động nộp bài.");
          setSubmitted(true);
          return 0;
        }
        return value - 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [submitted]);

  useEffect(() => {
    if (Object.keys(answers).length > 0 && !submitted) {
      const id = window.setTimeout(() => toast.success("Đã autosave đáp án.", { id: "autosave" }), 350);
      return () => window.clearTimeout(id);
    }
  }, [answers, submitted]);

  const currentQuestion = questions[currentQ - 1];

  const answeredCount = Object.values(answers).filter((answer) => Array.isArray(answer) ? answer.length > 0 : Boolean(answer)).length;

  const filteredQuestions = useMemo(() => {
    const all = Array.from({ length: totalQuestions }, (_, index) => index + 1);
    if (filter === "unanswered") {
      return all.filter((number) => {
        const answer = answers[number];
        return !answer || (Array.isArray(answer) && answer.length === 0);
      });
    }
    if (filter === "marked") return all.filter((number) => marked.includes(number));
    return all;
  }, [answers, filter, marked]);

  const formatTime = (seconds: number) => {
    const hour = Math.floor(seconds / 3600);
    const minute = Math.floor((seconds % 3600) / 60);
    const second = seconds % 60;
    return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:${String(second).padStart(2, "0")}`;
  };

  const setSingleAnswer = (value: string) => {
    setAnswers((current) => ({ ...current, [currentQ]: value }));
  };

  const setMultiAnswer = (value: string) => {
    setAnswers((current) => {
      const selected = Array.isArray(current[currentQ]) ? current[currentQ] as string[] : [];
      return {
        ...current,
        [currentQ]: selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value],
      };
    });
  };

  const markCurrent = () => {
    setMarked((current) => current.includes(currentQ) ? current.filter((number) => number !== currentQ) : [...current, currentQ]);
  };

  const submitQuiz = () => {
    setShowConfirm(false);
    setSubmitted(true);
    toast.success("Đã nộp bài. Kết quả đã được chấm tự động.");
  };

  const isAnswerCorrect = (questionId: number) => {
    const question = questions[questionId - 1];
    const answer = answers[questionId];
    if (!answer) return false;
    if (Array.isArray(question.correct)) {
      if (!Array.isArray(answer)) return false;
      return [...answer].sort().join("|") === [...question.correct].sort().join("|");
    }
    return String(answer).trim().toLowerCase() === String(question.correct).trim().toLowerCase();
  };

  const computedCorrect = questions.filter((question) => isAnswerCorrect(question.id)).length;
  const correctCount = answeredCount === 0 ? 26 : computedCorrect;
  const wrongCount = totalQuestions - correctCount;
  const score = ((correctCount / totalQuestions) * 10).toFixed(1);

  const sidebar = (
    <aside className={`absolute right-0 top-0 z-30 flex h-full w-[288px] shrink-0 flex-col border-l border-[#E5E7EB] bg-[#F9FAFB] transition-transform duration-300 lg:relative lg:translate-x-0 ${mobileMenuOpen ? "translate-x-0 shadow-2xl" : "translate-x-full"}`}>
      <div className="flex items-center justify-between border-b border-[#E5E7EB] bg-white p-4">
        <h3 className="font-black">Danh sách câu hỏi</h3>
        <button className="rounded p-1 text-[#6B7280] hover:bg-[#F7F7F8] lg:hidden" onClick={() => setMobileMenuOpen(false)}>
          <X className="h-5 w-5" />
        </button>
      </div>
      <div className="border-b border-[#E5E7EB] bg-white p-3">
        <div className="grid grid-cols-3 rounded-lg bg-[#F7F7F8] p-1">
          {[
            ["all", "Tất cả"],
            ["unanswered", "Chưa làm"],
            ["marked", "Đánh dấu"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={`rounded-md py-1.5 text-xs font-black ${filter === id ? "bg-white text-[#111827] shadow-sm" : "text-[#6B7280]"}`}
              onClick={() => setFilter(id as Filter)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-[10px] font-semibold text-[#6B7280]">
          <span className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm border bg-white" /> Chưa làm</span>
          <span className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm bg-[#C8102E]" /> Đã làm</span>
          <span className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm bg-[#FEF3C7]" /> Đánh dấu</span>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {filteredQuestions.length === 0 ? (
          <p className="mt-8 text-center text-sm text-[#6B7280]">Không có câu hỏi nào.</p>
        ) : (
          <div className="grid grid-cols-5 gap-2">
            {filteredQuestions.map((number) => {
              const answer = answers[number];
              const answered = answer && (!Array.isArray(answer) || answer.length > 0);
              const isMarked = marked.includes(number);
              const isCurrent = currentQ === number;
              let className = "border-[#E5E7EB] bg-white text-[#4B5563] hover:border-[#C8102E]";
              if (answered) className = "border-[#C8102E] bg-[#C8102E] text-white";
              if (isMarked) className = "border-[#F59E0B] bg-[#FEF3C7] text-[#B45309]";
              if (isCurrent) className = "border-[#C8102E] bg-white text-[#C8102E] ring-2 ring-[#C8102E]";
              return (
                <button
                  key={number}
                  className={`flex h-10 items-center justify-center rounded-md border text-sm font-black transition ${className}`}
                  onClick={() => {
                    setCurrentQ(number);
                    setMobileMenuOpen(false);
                  }}
                >
                  {number}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );

  if (submitted) {
    return (
      <div className="min-h-screen bg-[#F7F7F8] font-sans text-[#111827]">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-[#E5E7EB] bg-white px-4 md:px-6">
          <div className="min-w-0 text-sm font-bold text-[#6B7280]">
            <Link to="/workspace/1" className="hidden hover:text-[#111827] sm:inline">Kỹ thuật truyền thông</Link>
            <span className="hidden px-2 sm:inline">/</span>
            <span className="text-[#111827]">Kết quả: Quiz GK - Chương 1</span>
          </div>
          <Link to="/workspace/1">
            <Button variant="outline" size="sm">Thoát</Button>
          </Link>
        </header>

        <main className="mx-auto max-w-5xl px-4 py-8 md:px-6 md:py-12">
          <div className="mb-8 flex gap-4 overflow-x-auto border-b border-[#E5E7EB]">
            {[
              ["overview", "Tổng quan"],
              ["review", "Xem lại & Giải thích"],
              ["ai", "Hỏi AI"],
            ].map(([id, label]) => (
              <button
                key={id}
                className={`whitespace-nowrap border-b-2 pb-3 text-sm font-black transition ${resultTab === id ? "border-[#C8102E] text-[#C8102E]" : "border-transparent text-[#6B7280] hover:text-[#111827]"}`}
                onClick={() => setResultTab(id as ResultTab)}
              >
                {label}
              </button>
            ))}
          </div>

          {resultTab === "overview" && (
            <div className="grid gap-6 lg:grid-cols-[1fr_330px]">
              <Card className="border-[#BBF7D0] bg-gradient-to-br from-white to-[#F0FDF4] p-6 text-center md:p-8">
                <Trophy className="mx-auto mb-4 h-16 w-16 text-[#F59E0B]" />
                <h1 className="text-3xl font-black">Hoàn thành bài thi!</h1>
                <p className="mt-2 text-sm text-[#6B7280]">Bạn đã nộp bài vào {new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}</p>
                <div className="mt-8 grid grid-cols-2 gap-4 md:grid-cols-4">
                  {[
                    ["Điểm số", score, "text-[#C8102E]"],
                    ["Thời gian", formatTime(45 * 60 - timeLeft), "text-[#111827]"],
                    ["Câu đúng", correctCount, "text-[#16A34A]"],
                    ["Sai / bỏ trống", wrongCount, "text-[#DC2626]"],
                  ].map(([label, value, color]) => (
                    <Card key={String(label)} className="p-4">
                      <div className={`text-2xl font-black md:text-3xl ${color}`}>{value}</div>
                      <div className="mt-1 text-xs font-semibold text-[#6B7280]">{label}</div>
                    </Card>
                  ))}
                </div>
              </Card>

              <Card className="p-5">
                <h2 className="mb-4 font-black">Gợi ý ôn lại</h2>
                <div className="space-y-3">
                  {["Tầng giao vận TCP/UDP", "Lấy mẫu và lượng tử hóa", "Băng thông kênh thoại"].map((item, index) => (
                    <div key={item} className="rounded-md border border-[#E5E7EB] p-3">
                      <div className="text-sm font-black">{item}</div>
                      <div className="mt-2 h-2 rounded-full bg-[#F3F4F6]">
                        <div className="h-full rounded-full bg-[#C8102E]" style={{ width: `${[82, 64, 48][index]}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
                <Button className="mt-5 w-full" onClick={() => setResultTab("review")}>Xem câu sai</Button>
              </Card>
            </div>
          )}

          {resultTab === "review" && (
            <div className="space-y-5">
              {questions.slice(0, 6).map((question, index) => {
                const correct = answeredCount === 0 ? index !== 1 : isAnswerCorrect(question.id);
                const userAnswer = answers[question.id];
                return (
                  <Card key={question.id} className={`border-l-4 p-5 ${correct ? "border-l-[#16A34A]" : "border-l-[#DC2626]"}`}>
                    <div className="mb-4 flex items-start justify-between gap-4">
                      <div className="flex gap-3">
                        <span className={`font-black ${correct ? "text-[#16A34A]" : "text-[#DC2626]"}`}>Q{question.id}.</span>
                        <p className="font-bold">{question.text}</p>
                      </div>
                      <Badge className={correct ? "bg-[#F0FDF4] text-[#16A34A]" : "bg-[#FDE7EA] text-[#DC2626]"}>
                        {correct ? "Đúng" : "Sai"}
                      </Badge>
                    </div>
                    <div className="space-y-2 pl-8">
                      {!correct && (
                        <div className="flex gap-2 rounded-md border border-[#FECACA] bg-[#FEF2F2] p-3 text-sm">
                          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-[#DC2626]" />
                          <span><b>Đáp án của bạn:</b> {Array.isArray(userAnswer) ? userAnswer.join(", ") : userAnswer || "Chưa trả lời"}</span>
                        </div>
                      )}
                      <div className="flex gap-2 rounded-md border border-[#BBF7D0] bg-[#F0FDF4] p-3 text-sm">
                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[#16A34A]" />
                        <span><b>Đáp án đúng:</b> {Array.isArray(question.correct) ? question.correct.join(", ") : question.correct}</span>
                      </div>
                      <div className="rounded-md border border-[#E5E7EB] bg-white p-3 text-sm leading-6 text-[#4B5563]">
                        <b className="text-[#111827]">Giải thích từ AI:</b> {question.explanation}
                      </div>
                      <Button variant="outline" size="sm" onClick={() => toast.info("AI sẽ mở giải thích sâu hơn trong bản thật.")}>
                        <Bot className="h-4 w-4" />
                        Hỏi AI thêm về câu này
                      </Button>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}

          {resultTab === "ai" && (
            <Card className="mx-auto max-w-2xl p-6">
              <div className="mb-5 flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-md bg-[#FDE7EA] text-[#C8102E]">
                  <Bot className="h-5 w-5" />
                </div>
                <div>
                  <h1 className="font-black">Hỏi AI sau bài thi</h1>
                  <p className="text-sm text-[#6B7280]">Tập trung vào câu sai và phần kiến thức yếu.</p>
                </div>
              </div>
              <div className="space-y-3 rounded-lg bg-[#F9FAFB] p-4 text-sm">
                <div className="max-w-[85%] rounded-lg bg-white p-3 shadow-sm">Bạn sai nhiều ở phần TCP/UDP và PCM. Mình nên ôn lại từ đâu?</div>
                <div className="ml-auto max-w-[85%] rounded-lg bg-[#FDE7EA] p-3 font-semibold text-[#C8102E]">Tóm tắt giúp mình tầng giao vận.</div>
              </div>
              <div className="mt-4 flex gap-2">
                <Input placeholder="Nhập câu hỏi..." />
                <Button onClick={() => toast.info("AI chat đang ở chế độ demo.")}>Gửi</Button>
              </div>
            </Card>
          )}
        </main>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen max-w-full flex-col overflow-hidden bg-[#F7F7F8] font-sans text-[#111827]">
      <header className="z-20 flex h-16 shrink-0 items-center justify-between gap-2 border-b border-[#E5E7EB] bg-white px-3 md:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <button className="rounded-md p-1.5 text-[#6B7280] hover:bg-[#F7F7F8] lg:hidden" onClick={() => setMobileMenuOpen(true)}>
            <Menu className="h-5 w-5" />
          </button>
          <div className="min-w-0 truncate text-xs font-bold text-[#6B7280] sm:text-sm">
            <Link to="/workspace/1" className="hidden hover:text-[#111827] sm:inline">Chủ đề</Link>
            <span className="hidden px-2 sm:inline">/</span>
            <span className="inline-block max-w-[92px] truncate align-bottom text-[#111827] sm:max-w-[220px]">Quiz GK - Chương 1</span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5 md:gap-4">
          <span className="hidden items-center gap-1.5 text-xs font-bold text-[#6B7280] md:flex">
            <Save className="h-4 w-4" />
            Autosave
          </span>
          <div className={`flex items-center gap-1 rounded-md border px-2 py-1.5 font-mono text-xs font-black md:gap-2 md:px-3 md:text-lg ${timeLeft < 300 ? "border-[#FECACA] bg-[#FDE7EA] text-[#DC2626]" : "border-[#E5E7EB] bg-[#F7F7F8]"}`}>
            <Clock className="h-4 w-4" />
            {formatTime(timeLeft)}
          </div>
          <Button variant="danger" size="sm" className="px-2 sm:px-3" onClick={() => setShowConfirm(true)}>
            <span className="hidden sm:inline">Nộp bài</span>
            <span className="sm:hidden">Nộp</span>
          </Button>
        </div>
      </header>

      <div className="relative flex min-h-0 flex-1 overflow-hidden">
        <main className="flex min-w-0 flex-1 flex-col bg-white">
          <div className="min-h-0 flex-1 overflow-y-auto p-4 md:p-8 lg:p-12">
            <div className="mx-auto max-w-3xl">
              <div className="mb-8 flex items-center justify-between border-b border-[#E5E7EB] pb-4">
                <div>
                  <h1 className="text-2xl font-black">Câu {currentQ}/{totalQuestions}</h1>
                  <p className="mt-1 text-sm text-[#6B7280]">{currentQuestion.type === "multiple" ? "Chọn nhiều đáp án đúng" : currentQuestion.type === "fill" ? "Nhập câu trả lời ngắn" : "Chọn một đáp án đúng"}</p>
                </div>
                <button
                  onClick={markCurrent}
                  className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-black transition ${marked.includes(currentQ) ? "bg-[#FEF3C7] text-[#B45309]" : "bg-[#F7F7F8] text-[#6B7280] hover:text-[#111827]"}`}
                >
                  <Flag className={`h-4 w-4 ${marked.includes(currentQ) ? "fill-current" : ""}`} />
                  <span className="hidden sm:inline">Đánh dấu xem lại</span>
                </button>
              </div>

              <div className="mb-8 break-words text-lg font-bold leading-8">{currentQuestion.text}</div>

              <div className="space-y-3">
                {currentQuestion.type === "single" && currentQuestion.options.map((option) => (
                  <button
                    key={option}
                    className={`flex w-full items-center gap-4 rounded-lg border p-4 text-left transition ${
                      answers[currentQ] === option ? "border-[#C8102E] bg-[#FDE7EA] text-[#C8102E] ring-1 ring-[#C8102E]" : "border-[#E5E7EB] hover:border-[#C8102E]/50 hover:bg-[#F9FAFB]"
                    }`}
                    onClick={() => setSingleAnswer(option)}
                  >
                    <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${answers[currentQ] === option ? "border-[#C8102E]" : "border-[#9CA3AF]"}`}>
                      {answers[currentQ] === option && <span className="h-2.5 w-2.5 rounded-full bg-[#C8102E]" />}
                    </span>
                    <span className="font-semibold">{option}</span>
                  </button>
                ))}

                {currentQuestion.type === "multiple" && currentQuestion.options.map((option) => {
                  const selected = Array.isArray(answers[currentQ]) && (answers[currentQ] as string[]).includes(option);
                  return (
                    <button
                      key={option}
                      className={`flex w-full items-center gap-4 rounded-lg border p-4 text-left transition ${
                        selected ? "border-[#C8102E] bg-[#FDE7EA] text-[#C8102E] ring-1 ring-[#C8102E]" : "border-[#E5E7EB] hover:border-[#C8102E]/50 hover:bg-[#F9FAFB]"
                      }`}
                      onClick={() => setMultiAnswer(option)}
                    >
                      <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border ${selected ? "border-[#C8102E] bg-[#C8102E]" : "border-[#9CA3AF]"}`}>
                        {selected && <CheckCircle2 className="h-4 w-4 text-white" />}
                      </span>
                      <span className="font-semibold">{option}</span>
                    </button>
                  );
                })}

                {currentQuestion.type === "fill" && (
                  <Input
                    className="h-12 text-base"
                    placeholder="Nhập câu trả lời của bạn..."
                    value={typeof answers[currentQ] === "string" ? answers[currentQ] as string : ""}
                    onChange={(event) => setAnswers((current) => ({ ...current, [currentQ]: event.target.value }))}
                  />
                )}
              </div>
            </div>
          </div>

          <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-[#E5E7EB] bg-white p-3 md:p-4">
            <Button variant="outline" disabled={currentQ === 1} onClick={() => setCurrentQ((value) => Math.max(1, value - 1))}>
              <ChevronLeft className="h-4 w-4" />
              <span className="hidden sm:inline">Câu trước</span>
            </Button>
            <div className="min-w-0 flex-1 text-center text-xs font-bold text-[#6B7280] md:text-sm">
              Tiến độ: {answeredCount}/{totalQuestions}
              <div className="mx-auto mt-2 h-2 max-w-xs overflow-hidden rounded-full bg-[#F3F4F6]">
                <div className="h-full rounded-full bg-[#16A34A]" style={{ width: `${(answeredCount / totalQuestions) * 100}%` }} />
              </div>
            </div>
            <Button disabled={currentQ === totalQuestions} onClick={() => setCurrentQ((value) => Math.min(totalQuestions, value + 1))}>
              <span className="hidden sm:inline">Câu tiếp</span>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </footer>
        </main>

        {sidebar}

        {mobileMenuOpen && <button className="fixed inset-0 z-20 bg-black/25 lg:hidden" onClick={() => setMobileMenuOpen(false)} aria-label="Đóng danh sách câu hỏi" />}
      </div>

      {showConfirm && (
        <Modal title="Nộp bài thi?" onClose={() => setShowConfirm(false)} className="max-w-sm">
          <div className="p-5">
            <div className="mb-4 flex gap-3 rounded-lg bg-[#FFF4D9] p-3 text-sm">
              <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-[#C8102E]" />
              <p>Bạn đã hoàn thành <b>{answeredCount}/{totalQuestions}</b> câu. Sau khi nộp, bài sẽ được chấm ngay.</p>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowConfirm(false)}>Hủy</Button>
              <Button variant="danger" onClick={submitQuiz}>Đồng ý nộp</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
