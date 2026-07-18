import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock, Flag, Trophy, XCircle } from "lucide-react";
import { toast } from "sonner";
import { bkquizApi, type Attempt, type AttemptResult } from "../../api/bkquiz";
import { Badge, Button, Card, Checkbox, Input, Modal } from "../components/ui";

type AnswerValue = { selectedOptionIds: string[]; textAnswer: string };
const errorText = (error: unknown) =>
  error instanceof Error ? error.message : "Không thể tải bài làm.";
const formatTime = (seconds: number) =>
  `${String(Math.floor(seconds / 3600)).padStart(2, "0")}:${String(Math.floor((seconds % 3600) / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;

export default function QuizTaking() {
  const { id, attemptId } = useParams();
  const navigate = useNavigate();
  if (!attemptId)
    return (
      <AttemptStarter
        quizId={id ?? ""}
        onStarted={(attempt) =>
          navigate(`/attempt/${attempt.id}`, { replace: true })
        }
      />
    );
  return <AttemptSession attemptId={attemptId} />;
}

function AttemptStarter({
  quizId,
  onStarted,
}: {
  quizId: string;
  onStarted: (attempt: Attempt) => void;
}) {
  const quiz = useQuery({
    queryKey: ["quiz", quizId],
    queryFn: () => bkquizApi.quiz(quizId),
    enabled: Boolean(quizId),
  });
  const start = useMutation({
    mutationFn: () => bkquizApi.startAttempt(quizId),
    onSuccess: onStarted,
    onError: (error) => toast.error(errorText(error)),
  });
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#F7F7F8] p-5">
      <Card className="w-full max-w-lg p-7 text-center">
        {quiz.isLoading ? (
          "Đang tải quiz..."
        ) : quiz.error ? (
          <p className="text-red-700">{errorText(quiz.error)}</p>
        ) : (
          quiz.data && (
            <>
              <h1 className="text-2xl font-black">{quiz.data.title}</h1>
              <p className="mt-3 text-[#6B7280]">
                {quiz.data.questionCount} câu · {quiz.data.durationMinutes} phút
                · {quiz.data.difficulty}
              </p>
              <p className="mt-5 text-sm">
                Timer bắt đầu khi bạn xác nhận. Reload sau đó sẽ tiếp tục cùng
                lượt làm.
              </p>
              <Button
                className="mt-6"
                disabled={start.isPending}
                onClick={() => start.mutate()}
              >
                {start.isPending ? "Đang bắt đầu..." : "Bắt đầu làm bài"}
              </Button>
            </>
          )
        )}
      </Card>
    </div>
  );
}

function AttemptSession({ attemptId }: { attemptId: string }) {
  const client = useQueryClient();
  const [current, setCurrent] = useState(0);
  const [marked, setMarked] = useState<string[]>([]);
  const [answerEdits, setAnswerEdits] = useState<Record<string, AnswerValue>>({});
  const [dirty, setDirty] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [confirm, setConfirm] = useState(false);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const attemptQuery = useQuery({
    queryKey: ["attempt", attemptId],
    queryFn: () => bkquizApi.attempt(attemptId),
    enabled: !result,
  });
  const quiz = useQuery({
    queryKey: ["quiz", attemptQuery.data?.quizId],
    queryFn: () => bkquizApi.quiz(attemptQuery.data!.quizId),
    enabled: Boolean(attemptQuery.data?.quizId),
  });
  const preferences = useQuery({
    queryKey: ["preferences"],
    queryFn: bkquizApi.preferences,
  });
  const answers = useMemo<Record<string, AnswerValue>>(() => {
    const saved = Object.fromEntries(
      (attemptQuery.data?.answers ?? []).map((answer) => [answer.snapshotId, {
        selectedOptionIds: answer.selectedOptionIds ?? [], textAnswer: answer.textAnswer ?? "",
      }]),
    );
    return { ...saved, ...answerEdits };
  }, [answerEdits, attemptQuery.data?.answers]);
  useEffect(() => {
    const expiresAt = attemptQuery.data?.expiresAt;
    if (!expiresAt || result) return;
    const update = () =>
      setSeconds(
        Math.max(
          0,
          Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 1000),
        ),
      );
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [attemptQuery.data?.expiresAt, result]);
  const autosave = useMutation({
    mutationFn: async () => {
      const attempt = attemptQuery.data!;
      return bkquizApi.autosave(
        attemptId,
        attempt.version,
        Object.entries(answers).map(([snapshotId, value]) => ({
          snapshotId,
          ...value,
        })),
      );
    },
    onSuccess: (data) => { client.setQueryData(["attempt", attemptId], data); setAnswerEdits({}); setDirty(false); },
    onError: async (error) => {
      toast.error(errorText(error));
      await client.invalidateQueries({ queryKey: ["attempt", attemptId] });
    },
  });
  useEffect(() => {
    if (
      !dirty ||
      !preferences.data?.attemptAutosave ||
      !attemptQuery.data ||
      result
    )
      return;
    const timer = window.setTimeout(() => autosave.mutate(), 800);
    return () => window.clearTimeout(timer);
  }, [answers, attemptQuery.data, autosave, dirty, preferences.data?.attemptAutosave, result]);
  const submit = useMutation({
    mutationFn: async () => {
      if (preferences.data?.attemptAutosave) await autosave.mutateAsync();
      const storageKey = `bkquiz-submit-${attemptId}`;
      let key = sessionStorage.getItem(storageKey);
      if (!key) {
        key = crypto.randomUUID();
        sessionStorage.setItem(storageKey, key);
      }
      return bkquizApi.submit(attemptId, key);
    },
    onSuccess: (data) => {
      setResult(data);
      setConfirm(false);
      sessionStorage.removeItem(`bkquiz-submit-${attemptId}`);
      void client.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (error) => toast.error(errorText(error)),
  });
  useEffect(() => {
    if (
      seconds === 0 &&
      attemptQuery.data &&
      new Date(attemptQuery.data.expiresAt).getTime() <= Date.now() &&
      !result &&
      !submit.isPending
    )
      submit.mutate();
  }, [attemptQuery.data, result, seconds, submit]);
  if (attemptQuery.isLoading) return <Center text="Đang tải lượt làm bài..." />;
  if (attemptQuery.error || !attemptQuery.data)
    return <Center text={errorText(attemptQuery.error)} error />;
  const attempt = attemptQuery.data;
  if (attempt.status !== "IN_PROGRESS" && !result)
    return <ExistingResult attemptId={attemptId} />;
  if (result)
    return <ResultView result={result} {...(quiz.data?.title ? { quizTitle: quiz.data.title } : {})} />;
  const question = attempt.questions[current];
  if (!question) return <Center text="Quiz không có câu hỏi để làm." error />;
  const value = answers[question.snapshotId] ?? {
    selectedOptionIds: [],
    textAnswer: "",
  };
  const setValue = (next: AnswerValue) => { setDirty(true); setAnswerEdits((state) => ({ ...state, [question.snapshotId]: next })); };
  const answered = Object.values(answers).filter(
    (answer) => answer.selectedOptionIds.length || answer.textAnswer.trim(),
  ).length;
  return (
    <div className="flex min-h-screen flex-col bg-[#F7F7F8]">
      <header className="flex min-h-16 items-center justify-between gap-3 border-b bg-white px-4">
        <div>
          <b>{quiz.data?.title ?? "Quiz"}</b>
          <span className="ml-2 text-xs text-[#6B7280]">
            Đã trả lời {answered}/{attempt.questions.length}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Badge
            className={
              seconds < 300 ? "bg-red-50 text-red-700" : "bg-[#F3F4F6]"
            }
          >
            <Clock className="mr-1 h-4 w-4" />
            {formatTime(seconds)}
          </Badge>
          <Button variant="danger" size="sm" onClick={() => setConfirm(true)}>
            Nộp bài
          </Button>
        </div>
      </header>
      <div className="grid flex-1 lg:grid-cols-[1fr_280px]">
        <main className="p-5 md:p-10">
          <div className="mx-auto max-w-3xl">
            <div className="mb-6 flex justify-between">
              <div>
                <h1 className="text-2xl font-black">
                  Câu {current + 1}/{attempt.questions.length}
                </h1>
                <p className="text-sm text-[#6B7280]">{question.type}</p>
              </div>
              <button
                onClick={() =>
                  setMarked((items) =>
                    items.includes(question.snapshotId)
                      ? items.filter((id) => id !== question.snapshotId)
                      : [...items, question.snapshotId],
                  )
                }
                className={
                  marked.includes(question.snapshotId)
                    ? "text-amber-600"
                    : "text-[#6B7280]"
                }
              >
                <Flag className="h-5 w-5" />
              </button>
            </div>
            <Card className="p-6">
              <p className="mb-6 text-lg font-bold leading-8">
                {question.prompt}
              </p>
              {question.type === "FILL_BLANK" ? (
                <Input
                  value={value.textAnswer}
                  onChange={(e) =>
                    setValue({
                      selectedOptionIds: [],
                      textAnswer: e.target.value,
                    })
                  }
                  placeholder="Nhập câu trả lời..."
                />
              ) : (
                <div className="space-y-3">
                  {question.options.map((option) => {
                    const selected = value.selectedOptionIds.includes(
                      option.id,
                    );
                    return (
                      <label
                        key={option.id}
                        className={`flex cursor-pointer gap-3 rounded-md border p-4 ${selected ? "border-[#C8102E] bg-[#FDE7EA]" : ""}`}
                      >
                        <Checkbox
                          type={
                            question.type === "SINGLE_CHOICE"
                              ? "radio"
                              : "checkbox"
                          }
                          name={question.snapshotId}
                          checked={selected}
                          onChange={() =>
                            setValue({
                              textAnswer: "",
                              selectedOptionIds:
                                question.type === "SINGLE_CHOICE"
                                  ? [option.id]
                                  : selected
                                    ? value.selectedOptionIds.filter(
                                        (id) => id !== option.id,
                                      )
                                    : [...value.selectedOptionIds, option.id],
                            })
                          }
                        />
                        <span>{option.text}</span>
                      </label>
                    );
                  })}
                </div>
              )}
            </Card>
            <div className="mt-5 flex justify-between">
              <Button
                variant="outline"
                disabled={current === 0}
                onClick={() => setCurrent((index) => index - 1)}
              >
                Câu trước
              </Button>
              <Button
                disabled={current === attempt.questions.length - 1}
                onClick={() => setCurrent((index) => index + 1)}
              >
                Câu sau
              </Button>
            </div>
          </div>
        </main>
        <aside className="border-l bg-white p-4">
          <h2 className="mb-3 font-black">Danh sách câu hỏi</h2>
          <div className="grid grid-cols-5 gap-2">
            {attempt.questions.map((item, index) => {
              const answer = answers[item.snapshotId];
              const done = Boolean(
                answer?.selectedOptionIds.length || answer?.textAnswer.trim(),
              );
              return (
                <button
                  key={item.snapshotId}
                  onClick={() => setCurrent(index)}
                  className={`h-10 rounded-md border text-sm font-black ${index === current ? "ring-2 ring-[#C8102E]" : ""} ${done ? "bg-[#C8102E] text-white" : marked.includes(item.snapshotId) ? "bg-amber-100" : "bg-white"}`}
                >
                  {index + 1}
                </button>
              );
            })}
          </div>
          <p className="mt-5 text-xs text-[#6B7280]">
            {autosave.isPending
              ? "Đang tự động lưu..."
              : preferences.data?.attemptAutosave
                ? "Tự động lưu đang bật"
                : "Tự động lưu đang tắt"}
          </p>
        </aside>
      </div>
      {confirm && (
        <Modal title="Nộp bài?" onClose={() => setConfirm(false)}>
          <div className="p-5">
            <p>
              Bạn đã trả lời {answered}/{attempt.questions.length} câu.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setConfirm(false)}>
                Tiếp tục làm
              </Button>
              <Button
                disabled={submit.isPending}
                onClick={() => submit.mutate()}
              >
                {submit.isPending ? "Đang nộp..." : "Nộp bài"}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function ExistingResult({ attemptId }: { attemptId: string }) {
  const result = useQuery({
    queryKey: ["attempt-result", attemptId],
    queryFn: () => bkquizApi.result(attemptId),
  });
  return result.isLoading ? (
    <Center text="Đang tải kết quả..." />
  ) : result.error || !result.data ? (
    <Center text={errorText(result.error)} error />
  ) : (
    <ResultView result={result.data} />
  );
}
function ResultView({
  result,
  quizTitle,
}: {
  result: AttemptResult;
  quizTitle?: string | undefined;
}) {
  return (
    <div className="min-h-screen bg-[#F7F7F8] p-5 md:p-10">
      <div className="mx-auto max-w-4xl space-y-6">
        <Card className="p-8 text-center">
          <Trophy className="mx-auto h-14 w-14 text-amber-500" />
          <h1 className="mt-3 text-3xl font-black">
            {quizTitle || "Kết quả bài làm"}
          </h1>
          {result.percentage == null ? <p className="mt-6 rounded bg-amber-50 p-4 font-bold text-amber-800">Giáo viên đã ẩn điểm của bài làm này.</p> : <div className="mt-6 grid grid-cols-3 gap-3">
            <div>
              <b className="text-3xl text-[#C8102E]">
                {Number(result.percentage).toFixed(1)}%
              </b>
              <p>Điểm phần trăm</p>
            </div>
            <div>
              <b className="text-3xl">
                {result.score}/{result.maxScore}
              </b>
              <p>Điểm</p>
            </div>
            <div>
              <b className="text-3xl">{result.timedOut ? "Có" : "Không"}</b>
              <p>Hết giờ</p>
            </div>
          </div>}
        </Card>
        {result.answersReleased ? (
          <div className="space-y-3">
            {result.questions.map((item, index) => (
              <Card key={item.snapshotId} className="p-5">
                <div className="flex items-center gap-2">
                  {item.correct ? (
                    <CheckCircle2 className="text-green-600" />
                  ) : (
                    <XCircle className="text-red-600" />
                  )}
                  <b>
                    Câu {index + 1}: {item.awardedPoints}/{item.maxPoints} điểm
                  </b>
                </div>
                {item.correctOptionIds?.length ? (
                  <p className="mt-2 text-sm">
                    Đáp án đúng: {item.correctOptionIds.join(", ")}
                  </p>
                ) : null}
                {item.acceptedAnswers?.length ? (
                  <p className="mt-2 text-sm">
                    Đáp án chấp nhận: {item.acceptedAnswers.join(", ")}
                  </p>
                ) : null}
                {item.explanation && (
                  <p className="mt-2 text-sm text-[#6B7280]">
                    {item.explanation}
                  </p>
                )}
              </Card>
            ))}
          </div>
        ) : (
          <Card className="p-5 text-center">
            Đáp án chưa được công bố theo chính sách của bài.
          </Card>
        )}
        <div className="text-center">
          <Link to="/dashboard">
            <Button>Về Dashboard</Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
function Center({ text, error = false }: { text: string; error?: boolean }) {
  return (
    <div
      className={`flex min-h-screen items-center justify-center p-5 ${error ? "text-red-700" : "text-[#6B7280]"}`}
    >
      {text}
    </div>
  );
}
