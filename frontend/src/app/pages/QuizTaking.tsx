import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock, Flag, Trophy, XCircle } from "lucide-react";
import { toast } from "sonner";
import {
  bkquizApi,
  type AnswerFeedback,
  type Attempt,
  type AttemptResult,
} from "../../api/bkquiz";
import { citationLocation } from "./citationLocation";
import { questionVisualState } from "./attemptQuestionState";
import { Badge, Button, Card, Checkbox, Input, Modal } from "../components/ui";
import { cognitiveLabel } from "../lib/cognitive";
import { MathMarkdown } from "../components/MathMarkdown";

type AnswerValue = { selectedOptionIds: string[]; textAnswer: string };
const errorText = (error: unknown) =>
  error instanceof Error ? error.message : "Không thể tải bài làm.";
const formatTime = (seconds: number) =>
  `${String(Math.floor(seconds / 3600)).padStart(2, "0")}:${String(Math.floor((seconds % 3600) / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
const loadAttemptDraft = (attemptId: string): Record<string, AnswerValue> => {
  try {
    const raw = sessionStorage.getItem(`bkquiz-attempt-draft-${attemptId}`);
    return raw ? (JSON.parse(raw) as Record<string, AnswerValue>) : {};
  } catch {
    sessionStorage.removeItem(`bkquiz-attempt-draft-${attemptId}`);
    return {};
  }
};

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
  const [mode, setMode] = useState<"STANDARD" | "LIVE_FEEDBACK">("STANDARD");
  const quiz = useQuery({
    queryKey: ["quiz", quizId],
    queryFn: () => bkquizApi.quiz(quizId),
    enabled: Boolean(quizId),
  });
  const start = useMutation({
    mutationFn: () => bkquizApi.startAttempt(quizId, undefined, mode),
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
                · {cognitiveLabel(quiz.data.cognitiveMode)}
              </p>
              <p className="mt-5 text-sm">
                Timer bắt đầu khi bạn xác nhận. Reload sau đó sẽ tiếp tục cùng
                lượt làm.
              </p>
              <div className="mt-5 grid gap-3 text-left sm:grid-cols-2">
                <button
                  className={`rounded-lg border p-4 ${mode === "STANDARD" ? "border-[#C8102E] bg-[#FDE7EA]" : "bg-white"}`}
                  onClick={() => setMode("STANDARD")}
                >
                  <b>Làm bài tiêu chuẩn</b>
                  <span className="mt-1 block text-xs text-[#6B7280]">
                    Có thể sửa câu trả lời trước khi nộp bài.
                  </span>
                </button>
                <button
                  className={`rounded-lg border p-4 ${mode === "LIVE_FEEDBACK" ? "border-[#C8102E] bg-[#FDE7EA]" : "bg-white"}`}
                  onClick={() => setMode("LIVE_FEEDBACK")}
                >
                  <b>Học với đáp án trực tiếp</b>
                  <span className="mt-1 block text-xs text-[#6B7280]">
                    Xem đáp án sau khi xác nhận; câu đã xác nhận sẽ bị khóa.
                  </span>
                </button>
              </div>
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
  const draftKey = `bkquiz-attempt-draft-${attemptId}`;
  const [marked, setMarked] = useState<string[]>([]);
  const [activeQuestion, setActiveQuestion] = useState<string>();
  const [answerEdits, setAnswerEdits] = useState<Record<string, AnswerValue>>(
    () => loadAttemptDraft(attemptId),
  );
  const [saveErrors, setSaveErrors] = useState<Record<string, string>>({});
  const [feedbackEdits, setFeedbackEdits] = useState<Record<string, AnswerFeedback>>({});
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
      (attemptQuery.data?.answers ?? []).map((answer) => [
        answer.snapshotId,
        {
          selectedOptionIds: answer.selectedOptionIds ?? [],
          textAnswer: answer.textAnswer ?? "",
        },
      ]),
    );
    return { ...saved, ...answerEdits };
  }, [answerEdits, attemptQuery.data?.answers]);
  const feedback = useMemo(
    () => ({
      ...Object.fromEntries(
        (attemptQuery.data?.confirmedFeedback ?? []).map((item) => [
          item.snapshotId,
          item,
        ]),
      ),
      ...feedbackEdits,
    }),
    [attemptQuery.data?.confirmedFeedback, feedbackEdits],
  );
  useEffect(() => {
    if (Object.keys(answerEdits).length) {
      sessionStorage.setItem(draftKey, JSON.stringify(answerEdits));
    } else {
      sessionStorage.removeItem(draftKey);
    }
  }, [answerEdits, draftKey]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!Object.keys(answerEdits).length) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [answerEdits]);
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
  useEffect(() => {
    const questions = attemptQuery.data?.questions ?? [];
    if (!questions.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (visible) setActiveQuestion(visible.target.getAttribute("data-question-id") ?? undefined);
      },
      { rootMargin: "-20% 0px -65% 0px" },
    );
    questions.forEach((question) => {
      const element = document.getElementById(`question-${question.snapshotId}`);
      if (element) observer.observe(element);
    });
    return () => observer.disconnect();
  }, [attemptQuery.data?.questions]);
  const save = useMutation({
    mutationFn: async (snapshotIds: string[]) => {
      const attempt = attemptQuery.data!;
      const payload = Object.fromEntries(
        snapshotIds.map((snapshotId) => [
          snapshotId,
          answerEdits[snapshotId] ?? answers[snapshotId] ?? {
            selectedOptionIds: [],
            textAnswer: "",
          },
        ]),
      );
      const data = await bkquizApi.autosave(
        attemptId,
        attempt.version,
        Object.entries(payload).map(([snapshotId, value]) => ({
          snapshotId,
          ...value,
        })),
      );
      return { data, payload };
    },
    onSuccess: ({ data, payload }) => {
      client.setQueryData(["attempt", attemptId], data);
      setAnswerEdits((current) => {
        const next = { ...current };
        Object.entries(payload).forEach(([id, sent]) => {
          if (JSON.stringify(current[id]) === JSON.stringify(sent)) delete next[id];
        });
        return next;
      });
      setSaveErrors((current) => {
        const next = { ...current };
        Object.keys(payload).forEach((id) => delete next[id]);
        return next;
      });
    },
    onError: async (error, snapshotIds) => {
      setSaveErrors((current) => ({
        ...current,
        ...Object.fromEntries(snapshotIds.map((id) => [id, errorText(error)])),
      }));
      await client.invalidateQueries({ queryKey: ["attempt", attemptId] });
    },
  });
  useEffect(() => {
    const ids = Object.keys(answerEdits).filter((id) => !feedback[id]);
    if (
      !ids.length ||
      !preferences.data?.attemptAutosave ||
      !attemptQuery.data ||
      result ||
      save.isPending
    )
      return;
    const timer = window.setTimeout(() => save.mutate(ids), 800);
    return () => window.clearTimeout(timer);
  }, [answerEdits, attemptQuery.data, feedback, preferences.data?.attemptAutosave, result, save]);
  const confirmAnswer = useMutation({
    mutationFn: async ({ snapshotId, value }: { snapshotId: string; value: AnswerValue }) =>
      bkquizApi.confirmAnswer(
        attemptId,
        snapshotId,
        attemptQuery.data!.version,
        value,
      ),
    onSuccess: async (value) => {
      setFeedbackEdits((current) => ({ ...current, [value.snapshotId]: value }));
      setAnswerEdits((current) => {
        const next = { ...current };
        delete next[value.snapshotId];
        return next;
      });
      setSaveErrors((current) => {
        const next = { ...current };
        delete next[value.snapshotId];
        return next;
      });
      await client.invalidateQueries({ queryKey: ["attempt", attemptId] });
    },
    onError: async (error, variables) => {
      setSaveErrors((current) => ({
        ...current,
        [variables.snapshotId]: errorText(error),
      }));
      await client.invalidateQueries({ queryKey: ["attempt", attemptId] });
    },
  });
  const submit = useMutation({
    mutationFn: async () => {
      const dirtyIds = Object.keys(answerEdits).filter((id) => !feedback[id]);
      if (dirtyIds.length) await save.mutateAsync(dirtyIds);
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
      sessionStorage.removeItem(draftKey);
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
  if (!attempt.questions.length)
    return <Center text="Quiz không có câu hỏi để làm." error />;
  const answered = Object.values(answers).filter(
    (answer) => answer.selectedOptionIds.length || answer.textAnswer.trim(),
  ).length;
  const savedIds = new Set(attempt.answers.map((answer) => answer.snapshotId));
  const savedById = Object.fromEntries(
    attempt.answers.map((answer) => [answer.snapshotId, answer]),
  );
  const scrollTo = (snapshotId: string) => {
    document.getElementById(`question-${snapshotId}`)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };
  return (
    <div className="min-h-screen bg-[#F7F7F8]">
      <header className="sticky top-0 z-30 flex min-h-16 items-center justify-between gap-3 border-b bg-white px-4 shadow-sm">
        <div>
          <b>{quiz.data?.title ?? "Quiz"}</b>
          <span className="ml-2 text-xs text-[#6B7280]">
            Đã trả lời {answered}/{attempt.questions.length}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Badge className={seconds < 300 ? "bg-red-50 text-red-700" : "bg-[#F3F4F6]"}>
            <Clock className="mr-1 h-4 w-4" />
            {formatTime(seconds)}
          </Badge>
          <Button variant="danger" size="sm" onClick={() => setConfirm(true)}>
            Nộp bài
          </Button>
        </div>
      </header>
      <div className="mx-auto grid max-w-6xl gap-5 p-4 lg:grid-cols-[1fr_280px] lg:p-8">
        <QuestionNavigator
          className="lg:hidden"
          attempt={attempt}
          answers={answers}
          edits={answerEdits}
          feedback={feedback}
          marked={marked}
          activeQuestion={activeQuestion}
          onSelect={scrollTo}
        />
        <main className="space-y-6">
          {attempt.questions.map((question, index) => {
            const value = answers[question.snapshotId] ?? {
              selectedOptionIds: [],
              textAnswer: "",
            };
            const itemFeedback = feedback[question.snapshotId];
            const locked = Boolean(itemFeedback);
            const dirty = Boolean(answerEdits[question.snapshotId]);
            const hasAnswer = Boolean(
              value.selectedOptionIds.length || value.textAnswer.trim(),
            );
            const saving = save.isPending &&
              Boolean(save.variables?.includes(question.snapshotId));
            const setValue = (next: AnswerValue) => {
              if (locked) return;
              setAnswerEdits((state) => ({ ...state, [question.snapshotId]: next }));
            };
            return (
              <section
                id={`question-${question.snapshotId}`}
                data-question-id={question.snapshotId}
                key={question.snapshotId}
                className="scroll-mt-24"
              >
                <Card className="p-5 md:p-7">
                  <div className="mb-5 flex items-start justify-between gap-3">
                    <div>
                      <h2 className="text-xl font-black">
                        Câu {index + 1}/{attempt.questions.length}
                      </h2>
                      <p className="text-xs text-[#6B7280]">{question.type}</p>
                    </div>
                    <button
                      aria-label={`Đánh dấu câu ${index + 1}`}
                      onClick={() =>
                        setMarked((items) =>
                          items.includes(question.snapshotId)
                            ? items.filter((id) => id !== question.snapshotId)
                            : [...items, question.snapshotId],
                        )
                      }
                      className={marked.includes(question.snapshotId) ? "text-amber-600" : "text-[#6B7280]"}
                    >
                      <Flag className="h-5 w-5" />
                    </button>
                  </div>
                  <MathMarkdown className="mb-6 text-lg font-bold leading-8" normalizeLegacy>{question.prompt}</MathMarkdown>
                  {question.type === "FILL_BLANK" ? (
                    <Input
                      disabled={locked}
                      value={value.textAnswer}
                      onChange={(event) =>
                        setValue({ selectedOptionIds: [], textAnswer: event.target.value })
                      }
                      placeholder="Nhập câu trả lời..."
                    />
                  ) : (
                    <div className="space-y-3">
                      {question.options.map((option) => {
                        const selected = value.selectedOptionIds.includes(option.id);
                        return (
                          <label
                            key={option.id}
                            className={`flex gap-3 rounded-md border p-4 ${locked ? "cursor-not-allowed opacity-80" : "cursor-pointer"} ${selected ? "border-[#C8102E] bg-[#FDE7EA]" : ""}`}
                          >
                            <Checkbox
                              disabled={locked}
                              type={question.type === "SINGLE_CHOICE" ? "radio" : "checkbox"}
                              name={question.snapshotId}
                              checked={selected}
                              onChange={() =>
                                setValue({
                                  textAnswer: "",
                                  selectedOptionIds:
                                    question.type === "SINGLE_CHOICE"
                                      ? [option.id]
                                      : selected
                                        ? value.selectedOptionIds.filter((id) => id !== option.id)
                                        : [...value.selectedOptionIds, option.id],
                                })
                              }
                            />
                            <MathMarkdown inline normalizeLegacy>{option.text}</MathMarkdown>
                          </label>
                        );
                      })}
                    </div>
                  )}
                  <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t pt-4">
                    <span className="text-xs text-[#6B7280]">
                      {saving
                        ? "Đang lưu..."
                        : locked
                          ? `Đã xác nhận lúc ${new Date(itemFeedback!.confirmedAt).toLocaleTimeString("vi-VN")}`
                          : dirty
                            ? "Có thay đổi chưa lưu"
                            : savedIds.has(question.snapshotId)
                              ? `Đã lưu lúc ${new Date(savedById[question.snapshotId]!.answeredAt).toLocaleTimeString("vi-VN")}`
                              : "Chưa lưu"}
                    </span>
                    {!locked && (
                      <Button
                        disabled={
                          save.isPending ||
                          confirmAnswer.isPending ||
                          (attempt.mode === "LIVE_FEEDBACK" && !hasAnswer)
                        }
                        onClick={() =>
                          attempt.mode === "LIVE_FEEDBACK"
                            ? confirmAnswer.mutate({ snapshotId: question.snapshotId, value })
                            : save.mutate([question.snapshotId])
                        }
                      >
                        {attempt.mode === "LIVE_FEEDBACK"
                          ? "Xác nhận và xem đáp án"
                          : "Lưu câu trả lời"}
                      </Button>
                    )}
                  </div>
                  {saveErrors[question.snapshotId] && (
                    <div className="mt-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                      {saveErrors[question.snapshotId]}
                    </div>
                  )}
                  {itemFeedback && (
                    <LiveFeedbackView
                      feedback={itemFeedback}
                      question={question}
                    />
                  )}
                </Card>
              </section>
            );
          })}
          <Card className="p-6 text-center">
            <p className="font-bold">
              Đã trả lời {answered}/{attempt.questions.length} câu · còn{" "}
              {Object.keys(answerEdits).length} câu chưa đồng bộ
            </p>
            <Button className="mt-4" variant="danger" onClick={() => setConfirm(true)}>
              Nộp bài
            </Button>
          </Card>
        </main>
        <aside className="hidden lg:block">
          <QuestionNavigator
            className="sticky top-24"
            attempt={attempt}
            answers={answers}
            edits={answerEdits}
            feedback={feedback}
            marked={marked}
            activeQuestion={activeQuestion}
            onSelect={scrollTo}
          />
        </aside>
      </div>
      {confirm && (
        <Modal title="Nộp bài?" onClose={() => setConfirm(false)}>
          <div className="p-5">
            <p>Bạn đã trả lời {answered}/{attempt.questions.length} câu.</p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setConfirm(false)}>
                Tiếp tục làm
              </Button>
              <Button disabled={submit.isPending} onClick={() => submit.mutate()}>
                {submit.isPending ? "Đang nộp..." : "Nộp bài"}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function QuestionNavigator({
  className = "",
  attempt,
  answers,
  edits,
  feedback,
  marked,
  activeQuestion,
  onSelect,
}: {
  className?: string;
  attempt: Attempt;
  answers: Record<string, AnswerValue>;
  edits: Record<string, AnswerValue>;
  feedback: Record<string, AnswerFeedback>;
  marked: string[];
  activeQuestion: string | undefined;
  onSelect: (snapshotId: string) => void;
}) {
  const savedIds = new Set(attempt.answers.map((answer) => answer.snapshotId));
  return (
    <Card className={`p-4 ${className}`}>
      <h2 className="mb-3 font-black">Danh sách câu hỏi</h2>
      <div className="grid grid-cols-5 gap-2">
        {attempt.questions.map((item, index) => {
          const answer = answers[item.snapshotId];
          const hasAnswer = Boolean(
            answer?.selectedOptionIds.length || answer?.textAnswer.trim(),
          );
          const itemFeedback = feedback[item.snapshotId];
          const state = questionVisualState({
            hasAnswer,
            dirty: Boolean(edits[item.snapshotId]),
            saved: savedIds.has(item.snapshotId),
            ...(itemFeedback
              ? { confirmedCorrect: itemFeedback.correct }
              : {}),
          });
          const color = {
            CONFIRMED_CORRECT: "bg-green-600 text-white",
            CONFIRMED_INCORRECT: "bg-red-600 text-white",
            DIRTY: "bg-amber-100 text-amber-900",
            SAVED: "bg-[#C8102E] text-white",
            UNANSWERED: marked.includes(item.snapshotId)
              ? "bg-amber-100"
              : "bg-white",
          }[state];
          return (
            <button
              key={item.snapshotId}
              onClick={() => onSelect(item.snapshotId)}
              className={`h-10 rounded-md border text-sm font-black ${color} ${activeQuestion === item.snapshotId ? "ring-2 ring-[#111827] ring-offset-2" : ""}`}
            >
              {index + 1}
            </button>
          );
        })}
      </div>
      <div className="mt-4 space-y-1 text-xs text-[#6B7280]">
        <p>Đỏ thương hiệu: đã lưu · Vàng: chưa lưu</p>
        {attempt.mode === "LIVE_FEEDBACK" && <p>Xanh lá/đỏ: đã xác nhận đúng/sai</p>}
      </div>
    </Card>
  );
}

function LiveFeedbackView({
  feedback,
  question,
}: {
  feedback: AnswerFeedback;
  question: Attempt["questions"][number];
}) {
  const correctOptions = question.options
    .filter((option) => feedback.correctOptionIds.includes(option.id))
    .map((option) => option.text);
  return (
    <div className={`mt-4 rounded-lg border p-4 ${feedback.correct ? "border-green-200 bg-green-50" : "border-red-200 bg-red-50"}`}>
      <div className="flex items-center gap-2 font-black">
        {feedback.correct ? (
          <CheckCircle2 className="text-green-600" />
        ) : (
          <XCircle className="text-red-600" />
        )}
        {feedback.correct ? "Chính xác" : "Chưa chính xác"}
      </div>
      {correctOptions.length > 0 && (
        <div className="mt-2 flex gap-1 text-sm">Đáp án đúng: <MathMarkdown inline normalizeLegacy>{correctOptions.join(", ")}</MathMarkdown></div>
      )}
      {feedback.acceptedAnswers.length > 0 && (
        <div className="mt-2 flex gap-1 text-sm">
          Đáp án chấp nhận: <MathMarkdown inline normalizeLegacy>{feedback.acceptedAnswers.join(", ")}</MathMarkdown>
        </div>
      )}
      {(feedback.explanation || feedback.citations.length > 0) && (
        <details className="mt-3 rounded border bg-white p-3 text-sm">
          <summary className="cursor-pointer font-bold">Xem giải thích đáp án</summary>
          {feedback.explanation && <MathMarkdown className="mt-2" normalizeLegacy>{feedback.explanation}</MathMarkdown>}
          {feedback.citations
            .filter((citation) => citation.role !== "QUESTION")
            .map((citation) => (
              <blockquote
                key={`${citation.role}-${citation.sourceChunkId}`}
                className="mt-2 border-l-2 pl-3 text-[#6B7280]"
              >
                <b>{citation.filename} · {citationLocation(citation)}</b>
                <MathMarkdown className="block" normalizeLegacy>{citation.evidenceQuote}</MathMarkdown>
              </blockquote>
            ))}
        </details>
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
                  <div className="mt-2 flex gap-1 text-sm">
                    Đáp án chấp nhận: <MathMarkdown inline normalizeLegacy>{item.acceptedAnswers.join(", ")}</MathMarkdown>
                  </div>
                ) : null}
                {item.explanation && (
                  <MathMarkdown className="mt-2 text-sm text-[#6B7280]" normalizeLegacy>{item.explanation}</MathMarkdown>
                )}
                {item.citations?.length > 0 && (
                  <details className="mt-3 rounded border bg-gray-50 p-3 text-sm">
                    <summary className="cursor-pointer font-bold">Nguồn đáp án</summary>
                    {item.citations.filter((citation) => citation.role !== "QUESTION").map((citation) => (
                      <div key={`${citation.role}-${citation.sourceChunkId}`} className="mt-2">
                        <b>{citation.filename} · {citationLocation(citation)}</b>
                        {citation.heading && <span> · {citation.heading}</span>}
                        <blockquote className="mt-1 border-l-2 pl-2 text-[#6B7280]"><MathMarkdown normalizeLegacy>{citation.evidenceQuote}</MathMarkdown></blockquote>
                      </div>
                    ))}
                  </details>
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
