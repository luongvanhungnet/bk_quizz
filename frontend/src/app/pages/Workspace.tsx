import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  BookOpen,
  AlertTriangle,
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
  type CognitiveMode,
  type QuestionType,
  type Quiz,
  type Source,
  type Visibility,
} from "../../api/bkquiz";
import { cognitiveDistribution, cognitiveLabel, cognitiveOptions } from "../lib/cognitive";
import { ApiRequestError } from "../../api/client";
import { citationLocation } from "./citationLocation";
import { describeSourceProcessing } from "./sourceProcessing";
import { adaptivePollInterval } from "./polling";
import { describeQuizGenerationError } from "./quizGenerationError";
import { describeQuizBatchStatus } from "./quizBatchStatus";
import {
  describeAiValidationWarning,
  describeCitationWarningRole,
  isAiQualityWarningCode,
} from "./aiValidation";
import {
  QuizGenerationTimeline,
  mergeJobEvents,
} from "./QuizGenerationTimeline";
import { Badge, Button, Card, Checkbox, Input, Modal } from "../components/ui";
import { MathMarkdown } from "../components/MathMarkdown";

const message = (error: unknown) =>
  error instanceof Error ? error.message : "Thao tác thất bại.";
const formatBytes = (bytes: number) =>
  new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 }).format(
    bytes < 1024 * 1024 ? bytes / 1024 : bytes / (1024 * 1024),
  ) + (bytes < 1024 * 1024 ? " KB" : " MB");
const formatWaitingTime = (seconds: number) =>
  seconds < 60 ? `${seconds} giây` : `${Math.floor(seconds / 60)} phút`;

function WaitingTime({ createdAt }: { createdAt: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 10_000);
    return () => window.clearInterval(timer);
  }, []);
  const seconds = Math.max(
    0,
    Math.floor((now - new Date(createdAt).getTime()) / 1000),
  );
  return <>Đã chờ {formatWaitingTime(seconds)}</>;
}

export default function Workspace() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const uploadErrors = (location.state as { uploadErrors?: Array<{ name: string; message: string }> } | null)?.uploadErrors ?? [];
  const client = useQueryClient();
  const { user, resendVerification } = useAuth();
  const [selectedQuiz, setSelectedQuiz] = useState<string | null>(null);
  const [mode, setMode] = useState<"AI" | "MANUAL">("AI");
  const [activeJob, setActiveJob] = useState<{
    quizId: string;
    jobId: string;
  } | null>(null);
  const [viewJob, setViewJob] = useState<{
    quizId: string;
    jobId: string;
  } | null>(null);
  const [addSource, setAddSource] = useState(false);
  const [addQuestion, setAddQuestion] = useState(false);
  const [appendQuiz, setAppendQuiz] = useState(false);
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
    refetchInterval: (query) => {
      const terminal = !query.state.data?.some((source) =>
        ["UPLOADED", "SCANNING", "EXTRACTING", "EMBEDDING"].includes(source.status),
      );
      return adaptivePollInterval(
        query.state.dataUpdateCount,
        terminal,
        typeof document !== "undefined" && document.visibilityState === "hidden",
      );
    },
    refetchIntervalInBackground: false,
  });
  const quizzes = useQuery({
    queryKey: ["quizzes", id],
    queryFn: () => bkquizApi.quizzes(id),
    enabled: Boolean(id),
  });
  const activeQuizId = selectedQuiz ?? quizzes.data?.items[0]?.id ?? null;
  const activeQuiz = quizzes.data?.items.find(
    (quiz) => quiz.id === activeQuizId,
  );
  const questions = useQuery({
    queryKey: ["questions", activeQuizId],
    queryFn: () => bkquizApi.questions(activeQuizId!),
    enabled: Boolean(activeQuizId),
  });
  const generationJobs = useQuery({
    queryKey: ["quiz-generation-jobs", activeQuizId],
    queryFn: () => bkquizApi.quizGenerationJobs(activeQuizId!),
    enabled: Boolean(activeQuizId),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.some((item) =>
        ["QUEUED", "RUNNING", "RETRY"].includes(item.status),
      )
        ? 2_000
        : false,
    refetchIntervalInBackground: false,
  });
  const generationRunning = Boolean(
    generationJobs.data?.some((item) =>
      ["QUEUED", "RUNNING", "RETRY"].includes(item.status),
    ),
  );
  const effectiveJobId =
    (viewJob?.quizId === activeQuizId ? viewJob.jobId : null) ??
    (activeJob?.quizId === activeQuizId ? activeJob.jobId : null) ??
    generationJobs.data?.[0]?.id ??
    null;
  const job = useQuery({
    queryKey: ["job", effectiveJobId],
    queryFn: () => bkquizApi.job(effectiveJobId!),
    enabled: Boolean(effectiveJobId),
    refetchInterval: (query) =>
      adaptivePollInterval(
        query.state.dataUpdateCount,
        Boolean(query.state.data && ["SUCCEEDED", "FAILED"].includes(query.state.data.status)),
        typeof document !== "undefined" && document.visibilityState === "hidden",
      ),
    refetchIntervalInBackground: false,
  });
  const jobEventPage = useInfiniteQuery({
    queryKey: ["job-events", effectiveJobId],
    queryFn: ({ pageParam }) =>
      bkquizApi.jobEvents(effectiveJobId!, pageParam, 100),
    initialPageParam: 0,
    getNextPageParam: (page) =>
      page.hasMore ? page.nextCursor : undefined,
    enabled: Boolean(effectiveJobId),
    refetchInterval: (query) => {
      const jobTerminal =
        job.data && ["SUCCEEDED", "FAILED"].includes(job.data.status);
      const pages = query.state.data?.pages;
      const hasMore = pages?.[pages.length - 1]?.hasMore;
      return jobTerminal && !hasMore ? false : 2_000;
    },
    refetchIntervalInBackground: false,
  });
  const {
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = jobEventPage;
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage) {
      void fetchNextPage();
    }
  }, [
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  ]);
  const jobEvents = useMemo(
    () =>
      (jobEventPage.data?.pages ?? []).reduce(
        (current, page) => mergeJobEvents(current, page.items),
        [] as import("../../api/bkquiz").JobEvent[],
      ),
    [jobEventPage.data?.pages],
  );
  useEffect(() => {
    if (job.data?.status === "SUCCEEDED" && job.data.type === "QUIZ_GENERATION") {
      toast.success("Đã sinh quiz xong.");
      void client.invalidateQueries({ queryKey: ["quizzes", id] });
      void client.invalidateQueries({ queryKey: ["questions"] });
      void client.invalidateQueries({
        queryKey: ["quiz-generation-jobs", activeQuizId],
      });
    }
  }, [activeQuizId, client, id, job.data?.status, job.data?.type]);
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
  const retryGeneration = useMutation({
    mutationFn: bkquizApi.retryLastQuizGeneration,
    onSuccess: async (result) => {
      setSelectedQuiz(result.quiz.id);
      setActiveJob({ quizId: result.quiz.id, jobId: result.jobId });
      setViewJob({ quizId: result.quiz.id, jobId: result.jobId });
      await client.invalidateQueries({ queryKey: ["job", result.jobId] });
      await client.invalidateQueries({
        queryKey: ["quiz-generation-jobs", result.quiz.id],
      });
      await refresh();
      toast.success("Đã đưa yêu cầu sinh quiz trở lại hàng đợi.");
    },
    onError: (error) => toast.error(message(error)),
  });
  const reindexQuizSources = useMutation({
    mutationFn: async (quizId: string) => {
      const selected = await bkquizApi.quizSources(quizId);
      if (!selected.length) throw new Error("Quiz không còn tài liệu nguồn.");
      return Promise.all(selected.map((source) => bkquizApi.reindexSource(source.id)));
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["sources", id] });
      toast.success("Đã đưa tài liệu vào hàng đợi lập chỉ mục lại.");
    },
    onError: (error) => toast.error(message(error)),
  });
  if (topic.isLoading) return <Centered text="Đang tải Workspace..." />;
  if (topic.error || !topic.data)
    return <Centered text={message(topic.error)} error />;
  const currentQuiz = activeQuiz;
  const quizBatchStatus = describeQuizBatchStatus(
    job.data?.step,
    job.data?.availableAt,
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
      {uploadErrors.length > 0 && <div className="border-b border-red-200 bg-red-50 px-5 py-3 text-sm text-red-800">
        <b>Một số tài liệu chưa tải lên được:</b>
        <ul className="mt-1 list-disc pl-5">{uploadErrors.map((item) => <li key={item.name}><b>{item.name}:</b> {item.message}</li>)}</ul>
      </div>}
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
                {sources.data?.map((source) => {
                  const processing = describeSourceProcessing(source);
                  return (
                  <Card key={source.id} className="flex items-start gap-3 p-4">
                    <BookOpen className="h-5 w-5 text-[#C8102E]" />
                    <div className="min-w-0 flex-1">
                      <b className="block truncate text-sm">{source.name}</b>
                      <Badge className={
                        source.status === "READY"
                          ? "mt-1 bg-green-100 text-green-800"
                          : source.status === "FAILED"
                            ? "mt-1 bg-red-100 text-red-800"
                            : "mt-1 bg-blue-100 text-blue-800"
                      }>{processing.label}</Badge>
                      <span className="block text-xs text-[#6B7280]">
                        {source.contentType ?? "Không rõ định dạng"}
                        {source.sizeBytes != null ? ` · ${formatBytes(source.sizeBytes)}` : ""}
                        {source.chunkCount ? ` · ${source.chunkCount} đoạn` : ""}
                        {source.pageCount ? ` · ${source.pageCount} trang` : ""}
                      </span>
                      {!["READY", "FAILED", "DELETED"].includes(source.status) && (
                        <span className="block text-xs text-[#6B7280]">
                          <WaitingTime createdAt={source.createdAt} />
                        </span>
                      )}
                      {!["READY", "FAILED", "DELETED"].includes(source.status) && (
                        <div className="mt-2 h-1.5 overflow-hidden rounded bg-gray-100">
                          <div
                            className={`h-full bg-[#C8102E] ${source.indexingProgress === 0 ? "w-full animate-pulse opacity-50" : ""}`}
                            style={source.indexingProgress > 0 ? { width: `${source.indexingProgress}%` } : undefined}
                          />
                        </div>
                      )}
                      {source.indexingProgress > 0 && source.status !== "READY" && (
                        <span className="text-xs text-[#6B7280]">{source.indexingProgress}%</span>
                      )}
                      {source.mathExtractionStatus === "ENHANCED" && source.mathFormulaCount > 0 && (
                        <p className="mt-2 text-xs font-medium text-green-700">
                          Đã khôi phục {source.mathFormulaCount} công thức toán học.
                        </p>
                      )}
                      {(source.mathExtractionStatus === "PARTIAL" || source.mathExtractionStatus === "FAILED") && (
                        <div className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                          Một số công thức chưa được nhận dạng ({source.mathWarningCount} cảnh báo); tài liệu vẫn có thể sử dụng.
                        </div>
                      )}
                      {processing.warning && (
                        <div className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                          <b>DOCUMENT_PROCESSOR_UNAVAILABLE</b>
                          <p>{processing.warning}</p>
                          <Button size="sm" variant="outline" className="mt-2" onClick={() => void sources.refetch()}>
                            Kiểm tra lại
                          </Button>
                        </div>
                      )}
                      {source.errorCode && (
                        <div className="mt-2 rounded border border-red-200 bg-red-50 p-2 text-xs text-red-800">
                          <b>{source.errorCode}</b>
                          <p>{source.errorMessage ?? "Không thể xử lý tài liệu."}</p>
                        </div>
                      )}
                    </div>
                    {(source.status === "FAILED" || (source.status === "READY" && (!source.indexedAt || source.mathExtractionStatus === "PARTIAL" || source.mathExtractionStatus === "FAILED"))) && (
                      <Button size="sm" variant="outline" onClick={async () => {
                        try {
                          await bkquizApi.reindexSource(source.id);
                          toast.success("Đã xếp tài liệu vào hàng đợi xử lý.");
                          await refresh();
                        }
                        catch (error) { toast.error(message(error)); }
                      }}>Lập chỉ mục</Button>
                    )}
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
                  );
                })}
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
                  if ("jobId" in result) {
                    setActiveJob({
                      quizId: result.quiz.id,
                      jobId: result.jobId,
                    });
                    setViewJob({
                      quizId: result.quiz.id,
                      jobId: result.jobId,
                    });
                    await client.invalidateQueries({
                      queryKey: ["quiz-generation-jobs", result.quiz.id],
                    });
                  }
                  await refresh();
                  if ("quiz" in result) setSelectedQuiz(result.quiz.id);
                  else setSelectedQuiz(result.id);
                }}
              />
              {effectiveJobId && (
                <Card className="mt-3 border-blue-200 bg-blue-50 p-4 text-sm">
                  <b>{quizBatchStatus.label}</b>
                  {quizBatchStatus.detail && (
                    <p className="mt-1">{quizBatchStatus.detail}</p>
                  )}
                  <p className="mt-1 text-xs text-blue-800">
                    Job {job.data?.status ?? "QUEUED"} · lần thử{" "}
                    {job.data?.attempts ?? 0}/{job.data?.maxAttempts ?? 3}
                  </p>
                  <div className="mt-2 h-2 overflow-hidden rounded bg-blue-100"><div className="h-full bg-blue-600" style={{width:`${job.data?.progress ?? 0}%`}} /></div>
                  <p className="mt-1">{job.data?.progress ?? 0}%</p>
                  {generationJobs.data && generationJobs.data.length > 1 && (
                    <label className="mt-3 block text-xs font-bold">
                      Lần sinh Quiz
                      <select
                        className="mt-1 h-9 w-full rounded border bg-white px-2"
                        value={effectiveJobId ?? ""}
                        onChange={(event) =>
                          setViewJob({
                            quizId: activeQuizId!,
                            jobId: event.target.value,
                          })
                        }
                      >
                        {generationJobs.data.map((item) => (
                          <option key={item.id} value={item.id}>
                            {new Date(item.createdAt).toLocaleString("vi-VN")} ·{" "}
                            {item.status}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <QuizGenerationTimeline
                    events={jobEvents}
                    loading={jobEventPage.isLoading}
                  />
                  {job.data?.status === "RETRY" && job.data.errorCode && (
                    <p className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-amber-900">
                      Lỗi gần nhất: {job.data.errorMessage ?? job.data.errorCode}.
                      Hệ thống sẽ tự thử lại, bạn không cần giữ trang này mở.
                    </p>
                  )}
                  {job.data?.status === "FAILED" && job.data.errorCode && (() => {
                    const details = describeQuizGenerationError(job.data.errorCode);
                    const qualityWarning = isAiQualityWarningCode(job.data.errorCode);
                    return <div className={`mt-3 rounded border p-3 ${qualityWarning
                      ? "border-amber-200 bg-amber-50 text-amber-900"
                      : "border-red-200 bg-red-50 text-red-800"}`}>
                      <b>{details.title}</b>
                      <p>{details.message}</p>
                      {job.data.errorMessage && (
                        <p className="mt-1">{job.data.errorMessage}</p>
                      )}
                      <small className="block">Giai đoạn: {job.data.step ?? "FAILED"}</small>
                      <small className="block">Mã lỗi: {job.data.errorCode}</small>
                      {job.data.upstreamRequestId && (
                        <small className="block">Mã yêu cầu: {job.data.upstreamRequestId}</small>
                      )}
                      <div className="mt-3 flex flex-wrap gap-2">
                        {details.action === "REINDEX" && job.data.resourceId && (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={reindexQuizSources.isPending}
                            onClick={() => reindexQuizSources.mutate(job.data!.resourceId)}
                          >
                            Lập chỉ mục lại
                          </Button>
                        )}
                        {details.action === "RETRY" && job.data.resourceId && (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={retryGeneration.isPending}
                            onClick={() => retryGeneration.mutate(job.data!.resourceId)}
                          >
                            Thử lại
                          </Button>
                        )}
                        {details.action === "ADJUST" && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setMode("AI");
                              document.getElementById("quiz-form")?.scrollIntoView({
                                behavior: "smooth",
                                block: "start",
                              });
                            }}
                          >
                            Điều chỉnh và sinh lại
                          </Button>
                        )}
                      </div>
                    </div>;
                  })()}
                </Card>
              )}
            </section>
            {currentQuiz && (
              <section>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-xl font-black">{currentQuiz.title}</h2>
                    <p className="text-sm text-[#6B7280]">
                      {cognitiveLabel(currentQuiz.cognitiveMode)} · {currentQuiz.durationMinutes}{" "}
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
	                      disabled={generationRunning}
	                      onClick={() => setAddQuestion(true)}
                    >
                      <Plus className="h-4 w-4" />
                      Câu hỏi
	                    </Button>
	                    {["DRAFT", "READY"].includes(currentQuiz.status) &&
	                      currentQuiz.questionCount < 50 && (
	                        <Button
	                          size="sm"
	                          variant="outline"
	                          disabled={
	                            generationRunning || !user?.emailVerified
	                          }
	                          onClick={() => setAppendQuiz(true)}
	                        >
	                          <Bot className="h-4 w-4" />
	                          Sinh thêm bằng AI
	                        </Button>
	                      )}
	                    <Button
	                      size="sm"
	                      variant="danger"
	                      disabled={generationRunning}
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
                {currentQuiz.aiValidationStatus === "WARNING" && (
                  <Card className="mb-3 border-amber-300 bg-amber-50 p-4 text-amber-950">
                    <div className="flex gap-2">
                      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
                      <div>
                        <b>Kết quả AI đã được lưu nhưng cần kiểm tra</b>
                        <p className="mt-1 text-sm">
                          Quiz vẫn có thể chỉnh sửa, xuất bản và làm bài. Có {currentQuiz.aiValidationWarnings?.length ?? 0} cảnh báo chất lượng.
                        </p>
                        {(currentQuiz.aiValidationWarnings?.length ?? 0) > 0 && (
                          <ul className="mt-2 list-inside list-disc text-sm">
                            {[...new Set((currentQuiz.aiValidationWarnings ?? []).map((item) => item.code))].map((code) => (
                              <li key={code}>{describeAiValidationWarning(code)}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </div>
                  </Card>
                )}
                {currentQuiz.aiValidationStatus === "REVIEWED" && (
                  <Card className="border-blue-200 bg-blue-50 p-4 text-sm text-blue-950">
                    <b>Đã kiểm tra thủ công</b>
                    <p className="mt-1">Chủ Quiz đã xem các cảnh báo AI. Trạng thái này không thay thế nguồn được hệ thống xác minh.</p>
                  </Card>
                )}
                {currentQuiz.status === "FAILED" && (
                  <Card className="mb-3 border-red-200 p-4 text-red-700">
                    <b>
                      {describeQuizGenerationError(currentQuiz.errorCode).title}
                    </b>
                    <p>
                      {describeQuizGenerationError(currentQuiz.errorCode).message}
                    </p>
                    {currentQuiz.errorCode && (
                      <small>Mã lỗi: {currentQuiz.errorCode}</small>
                    )}
                  </Card>
                )}
                <div className="space-y-3">
                  {questions.data?.map((question, index) => (
                    <Card key={question.id} className="p-4">
                      <div className="flex justify-between gap-3">
                        <div>
                          <div className="font-bold">
                            <span>Câu {index + 1}. </span>
                            <MathMarkdown inline normalizeLegacy>{question.prompt}</MathMarkdown>
                          </div>
                          <p className="mt-2 text-xs text-[#6B7280]">
                            {question.type} · {question.points} điểm · {cognitiveLabel(question.cognitiveLevel)}
                          </p>
                          {question.complexityProfile?.verified && (
                            <details className="mt-2 rounded border bg-blue-50 p-2 text-xs">
                              <summary className="cursor-pointer font-bold">Thông tin độ phức tạp · D={question.complexityScore}</summary>
                              <p className="mt-1">Khái niệm: {question.complexityProfile.conceptCount} · Bước suy luận: {question.complexityProfile.reasoningStepCount}</p>
                              <p>Tình huống mới: {question.complexityProfile.requiresNovelScenario ? "Có" : "Không"} · So sánh: {question.complexityProfile.requiresComparison ? "Có" : "Không"}</p>
                            </details>
                          )}
                          {question.validationStatus === "WARNING" && (
                            <details className="mt-2 rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-950">
                              <summary className="cursor-pointer font-bold">
                                Câu hỏi cần kiểm tra · {question.validationWarnings?.length ?? 0} cảnh báo
                              </summary>
                              <ul className="mt-1 list-inside list-disc">
                                {Array.from(new Map((question.validationWarnings ?? []).map((warning) => [
                                  `${warning.code}-${warning.role ?? ""}`, warning,
                                ])).values()).map((warning) => (
                                  <li key={`${warning.code}-${warning.role ?? ""}`}>
                                    {warning.code === "INVALID_CITATION_QUOTE"
                                      ? describeCitationWarningRole(warning.role)
                                      : describeAiValidationWarning(warning.code)}
                                  </li>
                                ))}
                              </ul>
                              <Button className="mt-2" size="sm" variant="outline" onClick={async () => {
                                if (!window.confirm("Xác nhận bạn đã kiểm tra câu hỏi này? Thao tác không tạo nguồn trích dẫn đã xác minh.")) return;
                                const note = window.prompt("Ghi chú kiểm tra (không bắt buộc):") ?? "";
                                try {
                                  await bkquizApi.reviewQuestionValidation(question.id, note);
                                  await refresh();
                                  toast.success("Đã ghi nhận kiểm tra thủ công.");
                                } catch (error) {
                                  toast.error(message(error));
                                }
                              }}>Xác nhận đã kiểm tra</Button>
                            </details>
                          )}
                          {question.validationStatus === "REVIEWED" && (
                            <div className="mt-2 rounded border border-blue-200 bg-blue-50 p-2 text-xs text-blue-950">
                              <b>Đã được chủ Quiz kiểm tra thủ công</b>
                              {question.validationReviewedAt && <p className="mt-1">{new Date(question.validationReviewedAt).toLocaleString("vi-VN")}</p>}
                              {question.validationReviewNote && <p className="mt-1">Ghi chú: {question.validationReviewNote}</p>}
                              <p className="mt-1">{question.citations?.length
                                ? "Các nguồn hiện có vẫn được giữ; những cảnh báo còn lại đã được kiểm tra thủ công."
                                : "Chưa có trích dẫn được hệ thống xác minh."}</p>
                              <Button className="mt-2" size="sm" variant="outline" onClick={async () => {
                                try {
                                  await bkquizApi.undoQuestionValidationReview(question.id);
                                  await refresh();
                                } catch (error) {
                                  toast.error(message(error));
                                }
                              }}>Hoàn tác xác nhận</Button>
                            </div>
                          )}
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
                                  <span>{option.position + 1}. </span>
                                  <MathMarkdown inline normalizeLegacy>{option.text}</MathMarkdown>
                                </li>
                              ))}
                            </ul>
                          )}
                          {question.acceptedAnswers?.length > 0 && (
                            <div className="mt-2 flex gap-1 text-sm text-green-700">
                              <span>Đáp án:</span>
                              <MathMarkdown inline normalizeLegacy>{question.acceptedAnswers.join(", ")}</MathMarkdown>
                            </div>
                          )}
                          {question.explanation && (
                            <details className="mt-2 rounded border bg-gray-50 p-2 text-sm">
                              <summary className="cursor-pointer font-bold">Giải thích đáp án</summary>
                              <MathMarkdown className="mt-2 text-[#6B7280]" normalizeLegacy>{question.explanation}</MathMarkdown>
                            </details>
                          )}
                          {question.citations?.length > 0 && (
                            <div className="mt-3 grid gap-2 sm:grid-cols-2">
                              {(["QUESTION", "ANSWER"] as const).map((role) => {
                                const values = question.citations.filter((item) => role === "QUESTION"
                                  ? item.role === "QUESTION"
                                  : item.role === "ANSWER" || item.role === "EXPLANATION");
                                if (!values.length) return null;
                                return <details key={role} className="rounded border bg-gray-50 p-2 text-xs">
                                  <summary className="cursor-pointer font-bold">{role === "QUESTION" ? "Nguồn câu hỏi" : "Nguồn đáp án và giải thích"}</summary>
                                  {values.map((citation) => <div key={`${role}-${citation.sourceChunkId}`} className="mt-2">
                                    <b>{citation.filename} · {citationLocation(citation)}</b>
                                    {citation.heading && <span> · {citation.heading}</span>}
                                    <blockquote className="mt-1 border-l-2 pl-2 text-[#6B7280]"><MathMarkdown normalizeLegacy>{citation.evidenceQuote}</MathMarkdown></blockquote>
                                  </div>)}
                                </details>;
                              })}
                            </div>
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
            if (job) toast.success("Đã tải lên. Tài liệu đang chờ xử lý nền.");
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
      {appendQuiz && currentQuiz && (
        <AppendQuizModal
          quiz={currentQuiz}
          sources={sources.data ?? []}
          onClose={() => setAppendQuiz(false)}
          onCreated={async (result) => {
            setAppendQuiz(false);
            setActiveJob({
              quizId: result.quiz.id,
              jobId: result.jobId,
            });
            setViewJob({
              quizId: result.quiz.id,
              jobId: result.jobId,
            });
            await client.invalidateQueries({
              queryKey: ["quiz-generation-jobs", result.quiz.id],
            });
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
  sources: Source[];
  verified: boolean;
  onCreated: (result: Quiz | { quiz: Quiz; jobId: string }) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [cognitiveMode, setCognitiveMode] = useState<CognitiveMode>("BALANCED");
  const [duration, setDuration] = useState(45);
  const [visibility, setVisibility] = useState<Visibility>("PRIVATE");
  const [counts, setCounts] = useState({
    singleChoice: 10,
    multipleSelect: 5,
    fillBlank: 5,
  });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<ApiRequestError | null>(null);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const ready = sources.filter((source) => source.status === "READY" && source.indexedAt);
  const submit = async () => {
    if (!title.trim()) return toast.error("Nhập tên quiz.");
    if (mode === "AI" && !verified)
      return toast.error("Bạn cần xác minh email trước khi dùng AI.");
    if (mode === "AI" && selectedSources.length === 0)
      return toast.error("Hãy chọn ít nhất một tài liệu đã lập chỉ mục.");
    setSaving(true);
    setFormError(null);
    try {
      const result =
        mode === "AI"
          ? await bkquizApi.generateQuiz({
              topicId,
              sourceIds: selectedSources.slice(0, 10),
              title,
              cognitiveMode,
              durationMinutes: duration,
              visibility,
              questionCounts: counts,
            })
          : await bkquizApi.createQuiz({
              topicId,
              title,
              cognitiveMode,
              durationMinutes: duration,
              visibility,
            });
      await onCreated(result);
      setTitle("");
      toast.success(
        mode === "AI" ? "Đã gửi yêu cầu sinh quiz." : "Đã tạo quiz thủ công.",
      );
    } catch (e) {
      if (e instanceof ApiRequestError) setFormError(e);
      else toast.error(message(e));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Card id="quiz-form" className="grid gap-4 p-5 md:grid-cols-2">
      <label className="text-sm font-black md:col-span-2">
        Tên quiz
        <Input value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
	      <fieldset className="text-sm font-black md:col-span-2">
	        <legend>Mức độ tư duy</legend>
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          {cognitiveOptions.map((option) => (
            <label key={option.value} className={`cursor-pointer rounded-lg border p-3 ${cognitiveMode === option.value ? "border-blue-600 bg-blue-50" : "bg-white"}`}>
              <span className="flex items-center gap-2 font-bold">
                <input type="radio" name="cognitiveMode" value={option.value}
                  checked={cognitiveMode === option.value}
                  onChange={() => setCognitiveMode(option.value)} />
                {option.label}
              </span>
              <span className="mt-1 block text-xs text-slate-600">{option.description}</span>
	            </label>
          ))}
        </div>
        {cognitiveMode === "BALANCED" && (() => {
          const total = counts.singleChoice + counts.multipleSelect + counts.fillBlank;
          const distribution = cognitiveDistribution(total);
          return <div className="mt-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-700">
            <div className="flex flex-wrap gap-3">
              {(["L1", "L2", "L3", "L4", "L5"] as const).map((level) =>
                <span key={level}><b>{cognitiveLabel(level)}</b>: {distribution[level]} câu</span>)}
            </div>
            <p className="mt-2">Tỷ lệ 10% / 25% / 35% / 25% / 5% · {Math.ceil(total / 20)} nhóm Gemini</p>
          </div>;
        })()}
	      </fieldset>
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
        <div className="space-y-2 md:col-span-2">
          <b className="text-sm">Tài liệu dùng để sinh quiz</b>
          {ready.map((source) => <label key={source.id} className="flex items-center gap-2 rounded border p-2 text-sm">
            <Checkbox checked={selectedSources.includes(source.id)} onChange={(event) => setSelectedSources((current) => event.target.checked ? [...new Set([...current, source.id])] : current.filter((id) => id !== source.id))} />
            <span>{source.name} · {source.chunkCount} đoạn</span>
          </label>)}
          {!ready.length && <p className="text-sm text-amber-700">Chưa có tài liệu READY đã lập chỉ mục.</p>}
        </div>
      )}
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
      {formError && <div className="md:col-span-2"><ErrorPanel error={formError} /></div>}
    </Card>
  );
}

function AppendQuizModal({
  quiz,
  sources,
  onClose,
  onCreated,
}: {
  quiz: Quiz;
  sources: Source[];
  onClose: () => void;
  onCreated: (
    result: { quiz: Quiz; jobId: string },
  ) => Promise<void>;
}) {
  const remaining = Math.max(0, 50 - quiz.questionCount);
  const [cognitiveMode, setCognitiveMode] =
    useState<CognitiveMode>("BALANCED");
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [counts, setCounts] = useState({
    singleChoice: Math.min(5, remaining),
    multipleSelect: 0,
    fillBlank: 0,
  });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] =
    useState<ApiRequestError | null>(null);
  const readySources = sources.filter(
    (source) => source.status === "READY" && source.indexedAt,
  );
  const requested =
    counts.singleChoice + counts.multipleSelect + counts.fillBlank;

  const submit = async () => {
    if (selectedSources.length === 0) {
      toast.error("Hãy chọn ít nhất một tài liệu đã lập chỉ mục.");
      return;
    }
    if (requested < 1 || requested > remaining) {
      toast.error(`Bạn chỉ có thể thêm từ 1 đến ${remaining} câu.`);
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const result = await bkquizApi.appendQuizGeneration(quiz.id, {
        sourceIds: selectedSources.slice(0, 10),
        cognitiveMode,
        questionCounts: counts,
      });
      await onCreated(result);
      toast.success("Đã đưa yêu cầu sinh thêm câu hỏi vào hàng đợi.");
    } catch (error) {
      if (error instanceof ApiRequestError) setFormError(error);
      else toast.error(message(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title="Sinh thêm câu hỏi bằng AI"
      onClose={onClose}
      className="max-w-2xl"
    >
      <div className="max-h-[75vh] space-y-4 overflow-y-auto p-5">
        <p className="rounded bg-blue-50 p-3 text-sm text-blue-900">
          Quiz hiện có {quiz.questionCount} câu. Bạn còn có thể thêm tối đa{" "}
          <b>{remaining} câu</b>. Các câu cũ sẽ được giữ nguyên.
        </p>
        <label className="block text-sm font-bold">
          Mức độ tư duy
          <select
            className="mt-1 h-10 w-full rounded border bg-white px-3"
            value={cognitiveMode}
            onChange={(event) =>
              setCognitiveMode(event.target.value as CognitiveMode)
            }
          >
            {cognitiveOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="space-y-2">
          <legend className="text-sm font-bold">
            Tài liệu dùng để sinh câu hỏi
          </legend>
          {readySources.map((source) => (
            <label
              key={source.id}
              className="flex items-center gap-2 rounded border p-2 text-sm"
            >
              <Checkbox
                checked={selectedSources.includes(source.id)}
                onChange={(event) =>
                  setSelectedSources((current) =>
                    event.target.checked
                      ? [...new Set([...current, source.id])]
                      : current.filter((id) => id !== source.id),
                  )
                }
              />
              <span>
                {source.name} · {source.chunkCount} đoạn
              </span>
            </label>
          ))}
          {!readySources.length && (
            <p className="text-sm text-amber-700">
              Chưa có tài liệu sẵn sàng để sinh thêm câu hỏi.
            </p>
          )}
        </fieldset>
        <div className="grid grid-cols-3 gap-2">
          {(["singleChoice", "multipleSelect", "fillBlank"] as const)
            .map((key) => (
              <label key={key} className="text-xs font-bold">
                {key}
                <Input
                  type="number"
                  min={0}
                  max={remaining}
                  value={counts[key]}
                  onChange={(event) =>
                    setCounts((current) => ({
                      ...current,
                      [key]: Number(event.target.value),
                    }))
                  }
                />
              </label>
            ))}
        </div>
        <p className="text-sm">
          Sẽ thêm <b>{requested}</b> câu · còn lại{" "}
          <b>{Math.max(0, remaining - requested)}</b> chỗ.
        </p>
        {formError && <ErrorPanel error={formError} />}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Hủy
          </Button>
          <Button
            disabled={
              saving ||
              !readySources.length ||
              requested < 1 ||
              requested > remaining
            }
            onClick={submit}
          >
            {saving ? "Đang gửi..." : "Bắt đầu sinh thêm"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function ErrorPanel({ error }: { error: ApiRequestError }) {
  return <div className="mt-2 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
    <b>{error.code}</b><p>{error.message}</p>{error.traceId && <small>Mã yêu cầu: {error.traceId}</small>}
  </div>;
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
  const [sourceError, setSourceError] = useState<unknown>(null);
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
              setSourceError(null);
              try {
                const result = await bkquizApi.uploadSource(topicId, file);
                await onDone(result.jobId);
              } catch (error) {
                setSourceError(error);
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
        {sourceError instanceof ApiRequestError ? (
          <ErrorPanel error={sourceError} />
        ) : sourceError ? (
          <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            {message(sourceError)}
          </div>
        ) : null}
        <Button
          className="w-full"
          disabled={saving || text.trim().length < 100}
          onClick={async () => {
            setSaving(true);
            setSourceError(null);
            try {
              await bkquizApi.pasteSource(
                topicId,
                name || "Văn bản đã dán",
                text,
              );
              await onDone();
            } catch (error) {
              setSourceError(error);
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
        cognitiveLevel: quiz.cognitiveMode === "BALANCED" ? "L3" : quiz.cognitiveMode,
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
        {(prompt.trim() || options.some((value) => value.trim()) || explanation.trim()) && (
          <Card className="space-y-3 bg-gray-50 p-4">
            <b>Xem trước</b>
            {prompt.trim() && <MathMarkdown normalizeLegacy>{prompt}</MathMarkdown>}
            {type !== "FILL_BLANK" && options.map((value, index) => value.trim() && (
              <div key={`preview-${index}`} className="flex gap-2 text-sm">
                <span>{index + 1}.</span><MathMarkdown inline normalizeLegacy>{value}</MathMarkdown>
              </div>
            ))}
            {explanation.trim() && <MathMarkdown className="text-sm text-[#6B7280]" normalizeLegacy>{explanation}</MathMarkdown>}
          </Card>
        )}
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
