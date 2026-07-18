import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  Bot,
  FileQuestion,
  FileUp,
  Link as LinkIcon,
  Plus,
  Trash2,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "../../auth/AuthProvider";
import {
  bkquizApi,
  type Difficulty,
  type QuestionType,
  type Quiz,
  type Visibility,
} from "../../api/bkquiz";
import { Badge, Button, Card, Checkbox, Input, Modal } from "../components/ui";

const message = (error: unknown) =>
  error instanceof Error ? error.message : "Thao tác thất bại.";
export default function Workspace() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const { user, resendVerification } = useAuth();
  const [selectedQuiz, setSelectedQuiz] = useState<string | null>(null);
  const [mode, setMode] = useState<"AI" | "MANUAL">("AI");
  const [jobId, setJobId] = useState<string | null>(null);
  const [addSource, setAddSource] = useState(false);
  const [addQuestion, setAddQuestion] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [resendSending, setResendSending] = useState(false);
  const topic = useQuery({
    queryKey: ["topic", id],
    queryFn: () => bkquizApi.topic(id),
    enabled: Boolean(id),
  });
  const sources = useQuery({
    queryKey: ["sources", id],
    queryFn: () => bkquizApi.sources(id),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      query.state.data?.some((source) =>
        ["UPLOADED", "SCANNING", "EXTRACTING", "EMBEDDING"].includes(source.status),
      )
        ? 3000
        : false,
  });
  const quizzes = useQuery({
    queryKey: ["quizzes", id],
    queryFn: () => bkquizApi.quizzes(id),
    enabled: Boolean(id),
  });
  const activeQuizId = selectedQuiz ?? quizzes.data?.items[0]?.id ?? null;
  const questions = useQuery({
    queryKey: ["questions", activeQuizId],
    queryFn: () => bkquizApi.questions(activeQuizId!),
    enabled: Boolean(activeQuizId),
  });
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => bkquizApi.job(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) =>
      query.state.data &&
      ["SUCCEEDED", "FAILED"].includes(query.state.data.status)
        ? false
        : 2000,
  });
  useEffect(() => {
    if (job.data?.status === "SUCCEEDED") {
      toast.success("Đã xử lý xong.");
      void client.invalidateQueries({ queryKey: ["quizzes", id] });
      void client.invalidateQueries({ queryKey: ["questions"] });
    }
    if (job.data?.status === "FAILED")
      toast.error(job.data.errorMessage || "Job xử lý thất bại.");
  }, [client, id, job.data?.errorMessage, job.data?.status]);
  useEffect(() => {
    if (resendCooldown < 1) return;
    const timer = window.setTimeout(() => setResendCooldown((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [resendCooldown]);
  const refresh = async () =>
    Promise.all([
      client.invalidateQueries({ queryKey: ["topic", id] }),
      client.invalidateQueries({ queryKey: ["sources", id] }),
      client.invalidateQueries({ queryKey: ["quizzes", id] }),
      client.invalidateQueries({ queryKey: ["questions"] }),
      client.invalidateQueries({ queryKey: ["explore"] }),
      client.invalidateQueries({ queryKey: ["explore-topic", id] }),
    ]);
  const deleteQuiz = useMutation({
    mutationFn: bkquizApi.deleteQuiz,
    onSuccess: async () => {
      setSelectedQuiz(null);
      await refresh();
      toast.success("Đã xóa quiz.");
    },
    onError: (e) => toast.error(message(e)),
  });
  if (topic.isLoading) return <Centered text="Đang tải Workspace..." />;
  if (topic.error || !topic.data)
    return <Centered text={message(topic.error)} error />;
  const currentQuiz = quizzes.data?.items.find(
    (quiz) => quiz.id === activeQuizId,
  );
  return (
    <div className="min-h-screen bg-[#F7F7F8] text-[#111827]">
      <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b bg-white px-5 py-3">
        <div>
          <Link to="/dashboard" className="text-sm text-[#6B7280]">
            Dashboard /
          </Link>
          <h1 className="text-xl font-black">{topic.data.title}</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge className="bg-[#F3F4F6]">
            {topic.data.visibility === "PUBLIC" ? "Công khai" : "Riêng tư"}
          </Badge>
          <Badge className={topic.data.status === "PUBLISHED" ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"}>
            {topic.data.status === "PUBLISHED" ? "Đã xuất bản" : "Bản nháp"}
          </Badge>
          {topic.data.status !== "PUBLISHED" && (
            <Button
              size="sm"
              disabled={!user?.emailVerified}
              onClick={async () => {
                try {
                  await bkquizApi.publishTopic(id);
                  await refresh();
                } catch (e) {
                  toast.error(message(e));
                }
              }}
            >
              Xuất bản chủ đề
            </Button>
          )}
        </div>
      </header>
      {topic.data.visibility === "PUBLIC" && topic.data.status !== "PUBLISHED" && (
        <div className="border-b border-amber-200 bg-amber-50 px-5 py-3 text-sm text-amber-900">
          Chọn “Công khai” chỉ đặt quyền xem. Chủ đề chỉ xuất hiện trong Khám phá sau khi được xuất bản.
        </div>
      )}
      {!user?.emailVerified && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-red-200 bg-red-50 px-5 py-3 text-sm text-red-800">
          <span>Bạn cần xác minh email trước khi xuất bản chủ đề hoặc quiz.</span>
          <Button
            size="sm"
            variant="outline"
            disabled={resendSending || resendCooldown > 0 || !user?.email}
            onClick={async () => {
              if (!user?.email) return;
              setResendSending(true);
              try {
                await resendVerification(user.email);
                setResendCooldown(30);
                toast.success("Email xác minh mới đã được xếp hàng gửi.");
              } catch (error) {
                toast.error(message(error));
              } finally {
                setResendSending(false);
              }
            }}
          >
            {resendSending ? "Đang gửi..." : resendCooldown > 0 ? `Gửi lại sau ${resendCooldown}s` : "Gửi lại email xác minh"}
          </Button>
        </div>
      )}
      <div className="grid min-h-[calc(100vh-4rem)] lg:grid-cols-[260px_1fr_240px]">
        <aside className="border-r bg-white p-4">
          <h2 className="mb-3 font-black">
            Quiz ({quizzes.data?.items.length ?? 0})
          </h2>
          <div className="space-y-2">
            {quizzes.data?.items.map((quiz) => (
              <button
                key={quiz.id}
                onClick={() => setSelectedQuiz(quiz.id)}
                className={`w-full rounded-md border p-3 text-left ${activeQuizId === quiz.id ? "border-[#C8102E] bg-[#FDE7EA]" : "bg-white"}`}
              >
                <b className="line-clamp-2 text-sm">{quiz.title}</b>
                <span className="mt-1 block text-xs text-[#6B7280]">
                  {quiz.questionCount} câu · {quiz.status}
                </span>
              </button>
            ))}
            {!quizzes.isLoading && !quizzes.data?.items.length && (
              <p className="text-sm text-[#6B7280]">Chưa có quiz.</p>
            )}
          </div>
        </aside>
        <main className="min-w-0 p-5 md:p-8">
          <div className="mx-auto max-w-4xl space-y-6">
            <section>
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-black">Tài liệu nguồn</h2>
                  <p className="text-sm text-[#6B7280]">
                    Chỉ nguồn READY có thể dùng để sinh quiz.
                  </p>
                </div>
                <Button variant="outline" onClick={() => setAddSource(true)}>
                  <FileUp className="h-4 w-4" />
                  Thêm nguồn
                </Button>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {sources.data?.map((source) => (
                  <Card key={source.id} className="flex items-center gap-3 p-4">
                    <BookOpen className="h-5 w-5 text-[#C8102E]" />
                    <div className="min-w-0 flex-1">
                      <b className="block truncate text-sm">{source.name}</b>
                      <span className="text-xs text-[#6B7280]">
                        {source.status}
                        {source.errorMessage ? ` · ${source.errorMessage}` : ""}
                      </span>
                    </div>
                    <button
                      onClick={async () => {
                        try {
                          await bkquizApi.deleteSource(source.id);
                          await refresh();
                        } catch (e) {
                          toast.error(message(e));
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </button>
                  </Card>
                ))}
                {!sources.isLoading && !sources.data?.length && (
                  <Card className="p-5 text-sm text-[#6B7280]">
                    Chưa có tài liệu.
                  </Card>
                )}
              </div>
            </section>
            <section>
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-xl font-black">Tạo quiz</h2>
                <div className="flex rounded-md border bg-white p-1">
                  <button
                    className={`rounded px-3 py-1 text-sm font-bold ${mode === "AI" ? "bg-[#FDE7EA] text-[#C8102E]" : ""}`}
                    onClick={() => setMode("AI")}
                  >
                    Sinh bằng AI
                  </button>
                  <button
                    className={`rounded px-3 py-1 text-sm font-bold ${mode === "MANUAL" ? "bg-[#FDE7EA] text-[#C8102E]" : ""}`}
                    onClick={() => setMode("MANUAL")}
                  >
                    Thủ công
                  </button>
                </div>
              </div>
              <QuizForm
                mode={mode}
                topicId={id}
                sources={sources.data ?? []}
                verified={Boolean(user?.emailVerified)}
                onCreated={async (result) => {
                  if ("jobId" in result) setJobId(result.jobId);
                  await refresh();
                  if ("quiz" in result) setSelectedQuiz(result.quiz.id);
                  else setSelectedQuiz(result.id);
                }}
              />
              {jobId && (
                <Card className="mt-3 border-blue-200 bg-blue-50 p-4 text-sm">
                  Job {job.data?.status ?? "QUEUED"} · lần thử{" "}
                  {job.data?.attempts ?? 0}/{job.data?.maxAttempts ?? 3}
                </Card>
              )}
            </section>
            {currentQuiz && (
              <section>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-xl font-black">{currentQuiz.title}</h2>
                    <p className="text-sm text-[#6B7280]">
                      {currentQuiz.difficulty} · {currentQuiz.durationMinutes}{" "}
                      phút · {currentQuiz.status}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    {["DRAFT", "READY"].includes(currentQuiz.status) && (
                      <Button
                        size="sm"
                        disabled={
                          !user?.emailVerified ||
                          currentQuiz.questionCount === 0
                        }
                        onClick={async () => {
                          try {
                            await bkquizApi.publishQuiz(currentQuiz.id);
                            await refresh();
                          } catch (e) {
                            toast.error(message(e));
                          }
                        }}
                      >
                        Xuất bản
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setAddQuestion(true)}
                    >
                      <Plus className="h-4 w-4" />
                      Câu hỏi
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => deleteQuiz.mutate(currentQuiz.id)}
                    >
                      Xóa
                    </Button>
                    {currentQuiz.status === "PUBLISHED" && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => navigate(`/quizzes/${currentQuiz.id}/analytics`)}
                      >
                        Thống kê
                      </Button>
                    )}
                    {currentQuiz.status === "PUBLISHED" && (
                      <Button
                        size="sm"
                        onClick={() => navigate(`/quiz/${currentQuiz.id}/take`)}
                      >
                        Làm bài
                      </Button>
                    )}
                  </div>
                </div>
                {currentQuiz.status === "FAILED" && (
                  <Card className="mb-3 border-red-200 p-4 text-red-700">
                    {currentQuiz.errorMessage || currentQuiz.errorCode}
                  </Card>
                )}
                <div className="space-y-3">
                  {questions.data?.map((question, index) => (
                    <Card key={question.id} className="p-4">
                      <div className="flex justify-between gap-3">
                        <div>
                          <b>
                            Câu {index + 1}. {question.prompt}
                          </b>
                          <p className="mt-2 text-xs text-[#6B7280]">
                            {question.type} · {question.points} điểm
                          </p>
                          {question.options?.length > 0 && (
                            <ul className="mt-3 grid gap-1 text-sm sm:grid-cols-2">
                              {question.options.map((option) => (
                                <li
                                  key={option.id}
                                  className={
                                    option.correct
                                      ? "font-bold text-green-700"
                                      : ""
                                  }
                                >
                                  {option.position + 1}. {option.text}
                                </li>
                              ))}
                            </ul>
                          )}
                          {question.acceptedAnswers?.length > 0 && (
                            <p className="mt-2 text-sm text-green-700">
                              Đáp án: {question.acceptedAnswers.join(", ")}
                            </p>
                          )}
                        </div>
                        <button
                          onClick={async () => {
                            try {
                              await bkquizApi.deleteQuestion(question.id);
                              await refresh();
                            } catch (e) {
                              toast.error(message(e));
                            }
                          }}
                        >
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </button>
                      </div>
                    </Card>
                  ))}
                  {!questions.isLoading && !questions.data?.length && (
                    <Card className="p-6 text-center text-[#6B7280]">
                      Quiz chưa có câu hỏi.
                    </Card>
                  )}
                </div>
              </section>
            )}
          </div>
        </main>
        <aside className="border-l bg-white p-4">
          <h2 className="font-black">Công cụ</h2>
          {[
            [Bot, "AI Chat"],
            [LinkIcon, "Import URL"],
            [FileQuestion, "Export"],
            [Zap, "Thống kê nâng cao"],
          ].map(([Icon, label]) => {
            const I = Icon as typeof Bot;
            return (
              <button
                key={String(label)}
                disabled
                className="mt-3 flex w-full items-center gap-3 rounded-md border p-3 text-left text-sm"
              >
                <I className="h-4 w-4" />
                <span>
                  {String(label)}
                  <small className="block text-[#C8102E]">Sắp ra mắt</small>
                </span>
              </button>
            );
          })}
        </aside>
      </div>
      {addSource && (
        <SourceModal
          topicId={id}
          onClose={() => setAddSource(false)}
          onDone={async (job) => {
            setAddSource(false);
            if (job) setJobId(job);
            await refresh();
          }}
        />
      )}
      {addQuestion && currentQuiz && (
        <QuestionModal
          quiz={currentQuiz}
          onClose={() => setAddQuestion(false)}
          onDone={async () => {
            setAddQuestion(false);
            await refresh();
          }}
        />
      )}
    </div>
  );
}

function QuizForm({
  mode,
  topicId,
  sources,
  verified,
  onCreated,
}: {
  mode: "AI" | "MANUAL";
  topicId: string;
  sources: Array<{ id: string; status: string }>;
  verified: boolean;
  onCreated: (result: Quiz | { quiz: Quiz; jobId: string }) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty>("MIXED");
  const [duration, setDuration] = useState(45);
  const [visibility, setVisibility] = useState<Visibility>("PRIVATE");
  const [counts, setCounts] = useState({
    singleChoice: 10,
    multipleSelect: 5,
    fillBlank: 5,
  });
  const [saving, setSaving] = useState(false);
  const ready = sources
    .filter((source) => source.status === "READY")
    .map((source) => source.id);
  const submit = async () => {
    if (!title.trim()) return toast.error("Nhập tên quiz.");
    if (mode === "AI" && !verified)
      return toast.error("Bạn cần xác minh email trước khi dùng AI.");
    if (mode === "AI" && ready.length === 0)
      return toast.error("Cần ít nhất một tài liệu READY.");
    setSaving(true);
    try {
      const result =
        mode === "AI"
          ? await bkquizApi.generateQuiz({
              topicId,
              sourceIds: ready.slice(0, 10),
              title,
              difficulty,
              durationMinutes: duration,
              visibility,
              questionCounts: counts,
            })
          : await bkquizApi.createQuiz({
              topicId,
              title,
              difficulty,
              durationMinutes: duration,
              visibility,
            });
      await onCreated(result);
      setTitle("");
      toast.success(
        mode === "AI" ? "Đã gửi yêu cầu sinh quiz." : "Đã tạo quiz thủ công.",
      );
    } catch (e) {
      toast.error(message(e));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Card className="grid gap-4 p-5 md:grid-cols-2">
      <label className="text-sm font-black md:col-span-2">
        Tên quiz
        <Input value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="text-sm font-black">
        Độ khó
        <select
          className="mt-1 h-10 w-full rounded-md border bg-white px-3"
          value={difficulty}
          onChange={(e) => setDifficulty(e.target.value as Difficulty)}
        >
          {["EASY", "MEDIUM", "HARD", "MIXED"].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </label>
      <label className="text-sm font-black">
        Thời lượng
        <Input
          type="number"
          min={1}
          max={300}
          value={duration}
          onChange={(e) => setDuration(Number(e.target.value))}
        />
      </label>
      <label className="text-sm font-black">
        Hiển thị
        <select
          className="mt-1 h-10 w-full rounded-md border bg-white px-3"
          value={visibility}
          onChange={(e) => setVisibility(e.target.value as Visibility)}
        >
          <option value="PRIVATE">Riêng tư</option>
          <option value="PUBLIC">Công khai</option>
        </select>
      </label>
      {mode === "AI" && (
        <div className="grid grid-cols-3 gap-2 md:col-span-2">
          {(["singleChoice", "multipleSelect", "fillBlank"] as const).map(
            (key) => (
              <label key={key} className="text-xs font-bold">
                {key}
                <Input
                  type="number"
                  min={0}
                  max={50}
                  value={counts[key]}
                  onChange={(e) =>
                    setCounts((current) => ({
                      ...current,
                      [key]: Number(e.target.value),
                    }))
                  }
                />
              </label>
            ),
          )}
        </div>
      )}
      <Button disabled={saving} className="md:col-span-2" onClick={submit}>
        {saving
          ? "Đang xử lý..."
          : mode === "AI"
            ? "Sinh quiz bằng AI"
            : "Tạo quiz thủ công"}
      </Button>
    </Card>
  );
}

function SourceModal({
  topicId,
  onClose,
  onDone,
}: {
  topicId: string;
  onClose: () => void;
  onDone: (jobId?: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  return (
    <Modal title="Thêm tài liệu" onClose={onClose}>
      <div className="space-y-4 p-5">
        <label className="flex cursor-pointer flex-col items-center rounded-lg border-2 border-dashed p-6">
          <FileUp className="mb-2 h-7 w-7" />
          <b>Tải file</b>
          <input
            type="file"
            className="hidden"
            accept=".pdf,.docx,.pptx,.txt"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setSaving(true);
              try {
                const result = await bkquizApi.uploadSource(topicId, file);
                await onDone(result.jobId);
              } catch (error) {
                toast.error(message(error));
              } finally {
                setSaving(false);
              }
            }}
          />
        </label>
        <Input
          placeholder="Tên văn bản"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <textarea
          className="min-h-32 w-full rounded-md border p-3 text-sm"
          placeholder="Nội dung ít nhất 100 ký tự"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <Button
          className="w-full"
          disabled={saving || text.trim().length < 100}
          onClick={async () => {
            setSaving(true);
            try {
              await bkquizApi.pasteSource(
                topicId,
                name || "Văn bản đã dán",
                text,
              );
              await onDone();
            } catch (error) {
              toast.error(message(error));
            } finally {
              setSaving(false);
            }
          }}
        >
          Lưu văn bản
        </Button>
      </div>
    </Modal>
  );
}

function QuestionModal({
  quiz,
  onClose,
  onDone,
}: {
  quiz: Quiz;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const [type, setType] = useState<QuestionType>("SINGLE_CHOICE");
  const [prompt, setPrompt] = useState("");
  const [explanation, setExplanation] = useState("");
  const [options, setOptions] = useState(["", "", "", ""]);
  const [correct, setCorrect] = useState<number[]>([0]);
  const [answers, setAnswers] = useState("");
  const [saving, setSaving] = useState(false);
  const submit = async () => {
    setSaving(true);
    try {
      await bkquizApi.createQuestion(quiz.id, {
        type,
        prompt,
        explanation,
        points: 1,
        difficulty: quiz.difficulty,
        options:
          type === "FILL_BLANK"
            ? []
            : options.map((text, index) => ({
                text,
                correct: correct.includes(index),
              })),
        acceptedAnswers:
          type === "FILL_BLANK"
            ? answers
                .split("\n")
                .map((value) => value.trim())
                .filter(Boolean)
            : [],
      });
      await onDone();
      toast.success("Đã thêm câu hỏi.");
    } catch (e) {
      toast.error(message(e));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal title="Thêm câu hỏi" onClose={onClose} className="max-w-2xl">
      <div className="max-h-[75vh] space-y-4 overflow-y-auto p-5">
        <select
          className="h-10 w-full rounded-md border bg-white px-3"
          value={type}
          onChange={(e) => {
            const next = e.target.value as QuestionType;
            setType(next);
            setCorrect(next === "MULTIPLE_SELECT" ? [0, 1] : [0]);
          }}
        >
          {["SINGLE_CHOICE", "MULTIPLE_SELECT", "FILL_BLANK"].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
        <textarea
          className="min-h-24 w-full rounded-md border p-3"
          placeholder="Nội dung câu hỏi"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        {type !== "FILL_BLANK" ? (
          options.map((value, index) => (
            <div key={index} className="flex items-center gap-2">
              <Checkbox
                checked={correct.includes(index)}
                onChange={() =>
                  setCorrect((current) =>
                    type === "SINGLE_CHOICE"
                      ? [index]
                      : current.includes(index)
                        ? current.filter((i) => i !== index)
                        : [...current, index],
                  )
                }
              />
              <Input
                value={value}
                placeholder={`Lựa chọn ${index + 1}`}
                onChange={(e) =>
                  setOptions((current) =>
                    current.map((item, i) =>
                      i === index ? e.target.value : item,
                    ),
                  )
                }
              />
            </div>
          ))
        ) : (
          <textarea
            className="min-h-24 w-full rounded-md border p-3"
            placeholder="Mỗi đáp án chấp nhận trên một dòng"
            value={answers}
            onChange={(e) => setAnswers(e.target.value)}
          />
        )}
        <textarea
          className="min-h-20 w-full rounded-md border p-3"
          placeholder="Giải thích"
          value={explanation}
          onChange={(e) => setExplanation(e.target.value)}
        />
        <Button
          className="w-full"
          disabled={saving || !prompt.trim()}
          onClick={submit}
        >
          Lưu câu hỏi
        </Button>
      </div>
    </Modal>
  );
}
function Centered({ text, error = false }: { text: string; error?: boolean }) {
  return (
    <div
      className={`flex min-h-screen items-center justify-center p-6 ${error ? "text-red-700" : "text-[#6B7280]"}`}
    >
      {text}
    </div>
  );
}
