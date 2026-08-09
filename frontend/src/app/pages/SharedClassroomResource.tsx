import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  BookOpen,
  CalendarClock,
  Clock3,
  FileQuestion,
  Play,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import {
  bkquizApi,
  type SharedQuizDetail,
  type SharedTopicDetail,
} from "../../api/bkquiz";
import { Badge, Button, Card } from "../components/ui";
import { getAssignmentAvailability } from "./sharedResourceAvailability";
import { cognitiveLabel } from "../lib/cognitive";

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString("vi-VN") : "Không giới hạn";
}

function ErrorState({ error }: { error: unknown }) {
  const value = error as Error & { code?: string; traceId?: string };
  const revoked = value.code === "RESOURCE_SHARE_REVOKED";
  return (
    <Card className="mx-auto max-w-2xl p-8 text-center">
      <h1 className="text-xl font-black text-[#111827]">
        {revoked ? "Tài nguyên không còn được chia sẻ" : "Không thể mở tài nguyên"}
      </h1>
      <p className="mt-2 text-sm text-[#6B7280]">
        {value.message || "Bạn không có quyền hoặc tài nguyên không còn tồn tại."}
      </p>
      {value.traceId && (
        <p className="mt-2 text-xs text-[#9CA3AF]">
          Mã yêu cầu: {value.traceId}
        </p>
      )}
    </Card>
  );
}

export default function SharedClassroomResource() {
  const { classroomId = "", topicShareId, assignmentId } = useParams();
  const navigate = useNavigate();
  const [startError, setStartError] = useState<string>();
  const kind = topicShareId ? "TOPIC" : "QUIZ";
  const detail = useQuery<SharedTopicDetail | SharedQuizDetail>({
    queryKey: ["classroom-shared-resource", classroomId, kind, topicShareId ?? assignmentId],
    queryFn: () =>
      topicShareId
        ? bkquizApi.sharedTopic(classroomId, topicShareId)
        : bkquizApi.sharedQuiz(classroomId, assignmentId!),
    enabled: Boolean(classroomId && (topicShareId || assignmentId)),
  });
  const start = useMutation({
    mutationFn: async () => {
      if (!detail.data || !("assignment" in detail.data)) {
        throw new Error("Không tìm thấy thông tin bài được giao.");
      }
      return bkquizApi.startAttempt(detail.data.quiz.id, detail.data.assignment.id);
    },
    onSuccess: (attempt) => navigate(`/attempt/${attempt.id}`),
    onError: (error: Error) => setStartError(error.message),
  });

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-8">
      <Link
        to={`/classrooms/${classroomId}`}
        className="mb-5 inline-flex items-center gap-2 text-sm font-bold text-[#C8102E]"
      >
        <ArrowLeft className="h-4 w-4" />
        Quay lại lớp học
      </Link>
      {detail.isLoading ? (
        <Card className="p-10 text-center text-sm text-[#6B7280]">
          Đang tải thông tin tài nguyên...
        </Card>
      ) : detail.error ? (
        <ErrorState error={detail.error} />
      ) : detail.data && "topic" in detail.data ? (
        <TopicDetail data={detail.data} classroomId={classroomId} />
      ) : detail.data && "assignment" in detail.data ? (
        <QuizDetail
          data={detail.data}
          startError={startError}
          starting={start.isPending}
          onStart={() => {
            setStartError(undefined);
            start.mutate();
          }}
        />
      ) : (
        <ErrorState error={new Error("Tài nguyên không còn khả dụng.")} />
      )}
    </main>
  );
}

function TopicDetail({
  data,
  classroomId,
}: {
  data: Awaited<ReturnType<typeof bkquizApi.sharedTopic>>;
  classroomId: string;
}) {
  return (
    <div className="space-y-6">
      <Card className="p-6">
        <div className="flex items-center gap-3">
          <span className="rounded-xl bg-[#FDE7EA] p-3 text-[#C8102E]">
            <BookOpen className="h-6 w-6" />
          </span>
          <div>
            <Badge className="bg-[#FDE7EA] text-[#C8102E]">Chủ đề</Badge>
            <h1 className="mt-1 text-2xl font-black">{data.topic.title}</h1>
          </div>
        </div>
        <p className="mt-5 whitespace-pre-wrap text-[#4B5563]">
          {data.topic.description || "Chủ đề chưa có mô tả."}
        </p>
        <p className="mt-4 text-sm text-[#6B7280]">
          Chia sẻ bởi {data.preview.ownerUsername || "Người dùng"}
        </p>
      </Card>
      <section>
        <h2 className="mb-3 text-lg font-black">
          Quiz công khai trong chủ đề ({data.quizzes.length})
        </h2>
        {data.quizzes.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {data.quizzes.map((quiz) => (
              <Link key={quiz.id} to={`/quiz/${quiz.id}/take`}>
                <Card className="h-full p-4 transition hover:border-[#C8102E] hover:shadow-md">
                  <div className="flex items-start gap-3">
                    <FileQuestion className="mt-0.5 h-5 w-5 text-[#C8102E]" />
                    <div>
                      <h3 className="font-black">{quiz.title}</h3>
                      <p className="mt-1 text-xs text-[#6B7280]">
                        {quiz.questionCount} câu · {quiz.durationMinutes} phút ·{" "}
                        {cognitiveLabel(quiz.cognitiveMode)}
                      </p>
                    </div>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        ) : (
          <Card className="p-6 text-center text-sm text-[#6B7280]">
            Chủ đề chưa có Quiz công khai đã xuất bản.
          </Card>
        )}
        <p className="mt-3 text-xs text-[#9CA3AF]">
          Các Quiz riêng tư chỉ xuất hiện khi được giao riêng cho lớp học.
        </p>
      </section>
      <Link
        className="sr-only"
        to={`/classrooms/${classroomId}`}
        aria-hidden="true"
      >
        Lớp học
      </Link>
    </div>
  );
}

function QuizDetail({
  data,
  startError,
  starting,
  onStart,
}: {
  data: Awaited<ReturnType<typeof bkquizApi.sharedQuiz>>;
  startError: string | undefined;
  starting: boolean;
  onStart: () => void;
}) {
  const { assignment, quiz } = data;
  const availability = getAssignmentAvailability(assignment);
  const disabledReason = availability.reason;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <Card className="p-6">
        <div className="flex items-center gap-3">
          <span className="rounded-xl bg-[#FDE7EA] p-3 text-[#C8102E]">
            <FileQuestion className="h-6 w-6" />
          </span>
          <div>
            <Badge className="bg-[#FDE7EA] text-[#C8102E]">Quiz</Badge>
            <h1 className="mt-1 text-2xl font-black">{quiz.title}</h1>
          </div>
        </div>
        <p className="mt-5 whitespace-pre-wrap text-[#4B5563]">
          {quiz.description || assignment.instructions || "Quiz chưa có mô tả."}
        </p>
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          <Info label="Số câu" value={`${quiz.questionCount}`} />
          <Info label="Mức độ tư duy" value={cognitiveLabel(quiz.cognitiveMode)} />
          <Info label="Thời lượng" value={`${assignment.durationMinutes} phút`} />
        </div>
      </Card>
      <Card className="h-fit space-y-4 p-5">
        <h2 className="font-black">Quy định làm bài</h2>
        <p className="flex gap-2 text-sm">
          <CalendarClock className="h-4 w-4 text-[#C8102E]" />
          Mở: {formatDate(assignment.opensAt)}
        </p>
        <p className="flex gap-2 text-sm">
          <CalendarClock className="h-4 w-4 text-[#C8102E]" />
          Hạn: {formatDate(assignment.dueAt)}
        </p>
        <p className="flex gap-2 text-sm">
          <Clock3 className="h-4 w-4 text-[#C8102E]" />
          Tối đa {assignment.maxAttempts} lượt
        </p>
        {disabledReason && (
          <p className="rounded bg-[#FFF8E8] p-3 text-sm text-[#92400E]">
            {disabledReason}
          </p>
        )}
        {startError && (
          <p className="rounded bg-red-50 p-3 text-sm text-red-700">
            {startError}
          </p>
        )}
        <Button
          className="w-full"
          disabled={Boolean(disabledReason) || starting}
          onClick={onStart}
        >
          <Play className="h-4 w-4" />
          {starting ? "Đang bắt đầu..." : "Làm quiz"}
        </Button>
      </Card>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-[#F7F7F8] p-3">
      <p className="text-xs text-[#6B7280]">{label}</p>
      <p className="mt-1 font-black">{value}</p>
    </div>
  );
}
