import { BookOpen, Clock3, FileQuestion, LockKeyhole } from "lucide-react";
import { Link } from "react-router";
import type { SharedResourcePreview } from "../../api/bkquiz";
import { Badge, Card } from "./ui";

export function SharedResourceCard({
  classroomId,
  preview,
}: {
  classroomId: string;
  preview: SharedResourcePreview;
}) {
  if (!preview.available || !preview.referenceId) {
    return (
      <Card className="mt-2 flex gap-3 border-dashed bg-[#F7F7F8] p-3 text-[#6B7280]">
        <LockKeyhole className="mt-0.5 h-5 w-5 shrink-0" />
        <div>
          <p className="text-sm font-bold">Tài nguyên không còn khả dụng</p>
          <p className="text-xs">
            Tài nguyên có thể đã bị thu hồi, ẩn hoặc xóa.
          </p>
        </div>
      </Card>
    );
  }

  const topic = preview.kind === "TOPIC";
  const href = topic
    ? `/classrooms/${classroomId}/resources/topics/${preview.referenceId}`
    : `/classrooms/${classroomId}/resources/quizzes/${preview.referenceId}`;
  return (
    <Link
      to={href}
      className="mt-2 block rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8102E]"
      aria-label={`Xem chi tiết ${topic ? "chủ đề" : "Quiz"} ${preview.title}`}
    >
      <Card className="border-[#E5C9CE] bg-white p-3 transition hover:border-[#C8102E] hover:shadow-md">
        <div className="flex items-start gap-3">
          <span className="rounded-lg bg-[#FDE7EA] p-2 text-[#C8102E]">
            {topic ? (
              <BookOpen className="h-5 w-5" />
            ) : (
              <FileQuestion className="h-5 w-5" />
            )}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className="bg-[#FDE7EA] text-[#C8102E]">
                {topic ? "Chủ đề" : "Quiz"}
              </Badge>
              {preview.assignmentStatus && (
                <Badge className="bg-[#F7F7F8] text-[#374151]">
                  {preview.assignmentStatus === "PUBLISHED"
                    ? "Đang mở"
                    : preview.assignmentStatus === "CLOSED"
                      ? "Đã đóng"
                      : "Bản nháp"}
                </Badge>
              )}
            </div>
            <h3 className="mt-2 truncate text-sm font-black text-[#111827]">
              {preview.title}
            </h3>
            {preview.description && (
              <p className="mt-1 line-clamp-2 text-xs text-[#6B7280]">
                {preview.description}
              </p>
            )}
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-[#6B7280]">
              {preview.ownerUsername && <span>{preview.ownerUsername}</span>}
              <span>
                {topic
                  ? `${preview.quizCount} Quiz`
                  : `${preview.questionCount} câu hỏi`}
              </span>
              {!topic && preview.durationMinutes != null && (
                <span className="inline-flex items-center gap-1">
                  <Clock3 className="h-3 w-3" />
                  {preview.durationMinutes} phút
                </span>
              )}
            </div>
          </div>
        </div>
      </Card>
    </Link>
  );
}
