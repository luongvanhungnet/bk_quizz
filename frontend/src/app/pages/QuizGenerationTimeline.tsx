import {
  AlertTriangle,
  ArrowDown,
  CheckCircle2,
  CircleX,
  Info,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { JobEvent, JobEventLevel } from "../../api/bkquiz";
import { Button } from "../components/ui";
import { isAiQualityWarningCode } from "./aiValidation";

const styles: Record<JobEventLevel, string> = {
  INFO: "border-blue-200 bg-blue-50 text-blue-900",
  WARNING: "border-amber-200 bg-amber-50 text-amber-950",
  ERROR: "border-red-200 bg-red-50 text-red-900",
  SUCCESS: "border-emerald-200 bg-emerald-50 text-emerald-900",
};

const icons = {
  INFO: Info,
  WARNING: AlertTriangle,
  ERROR: CircleX,
  SUCCESS: CheckCircle2,
} satisfies Record<JobEventLevel, typeof Info>;

const providerLabels: Record<string, string> = {
  gemini_oauth: "Gemini OAuth",
  gemini_api_key: "Gemini API",
  ollama: "Ollama Qwen",
};

const cognitiveReasonLabels: Record<string, string> = {
  LEVEL_MISMATCH: "Sai mức độ tư duy",
  CONCEPT_COUNT_OUT_OF_RANGE: "Số khái niệm ngoài khoảng",
  REASONING_STEPS_OUT_OF_RANGE: "Số bước suy luận ngoài khoảng",
  NOVEL_SCENARIO_REQUIRED: "Thiếu tình huống mới",
  NOVEL_SCENARIO_NOT_ALLOWED: "Có tình huống mới không phù hợp",
  DIRECT_ANSWER_REQUIRED: "Đáp án chưa xuất hiện trực tiếp trong nguồn",
  DIRECT_ANSWER_NOT_ALLOWED: "Đáp án còn xuất hiện trực tiếp trong nguồn",
  COMPARISON_REQUIRED: "Thiếu yêu cầu so sánh",
  COMPARISON_NOT_ALLOWED: "Có yêu cầu so sánh không phù hợp",
  SCORE_OUT_OF_RANGE: "Điểm phức tạp ngoài khoảng",
  SCENARIO_NOT_NOVEL: "Tình huống chưa đủ mới",
  L1_ANSWER_NOT_IN_EVIDENCE: "Đáp án L1 chưa có trong trích dẫn",
};

function metadataCount(
  metadata: Record<string, unknown>,
  key: string,
): number | null {
  const value = metadata[key];
  return typeof value === "number" && Number.isInteger(value) && value >= 0
    ? value
    : null;
}

function metadataText(
  metadata: Record<string, unknown>,
  key: string,
): string | null {
  const value = metadata[key];
  return typeof value === "string" && value.length > 0 && value.length <= 160
    ? value
    : null;
}

function cognitiveFailureDistribution(
  metadata: Record<string, unknown>,
): Array<[string, number]> {
  const value = metadata.failureDistribution;
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];
  return Object.entries(value).filter(
    (entry): entry is [string, number] =>
      typeof entry[1] === "number" && Number.isFinite(entry[1]) && entry[1] > 0,
  );
}

interface ValidationErrorItem {
  field: string;
  message: string;
  type: string;
}

const validationTypeMessages: Record<string, string> = {
  list_type: "phải là một danh sách.",
  missing: "là trường bắt buộc.",
  string_type: "phải là chuỗi ký tự.",
  int_type: "phải là số nguyên.",
  bool_type: "phải là giá trị đúng hoặc sai.",
};

function validationMessage(error: ValidationErrorItem): string {
  return validationTypeMessages[error.type] ?? error.message;
}

function validationErrors(
  metadata: Record<string, unknown>,
): ValidationErrorItem[] {
  const value = metadata.validationErrors;
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const candidate = item as Record<string, unknown>;
    if (
      typeof candidate.field !== "string" ||
      typeof candidate.message !== "string" ||
      typeof candidate.type !== "string"
    ) {
      return [];
    }
    return [{
      field: candidate.field,
      message: candidate.message,
      type: candidate.type,
    }];
  });
}

function visibleIndex(value: unknown): number | null {
  return typeof value === "number" &&
    Number.isFinite(value) &&
    Number.isInteger(value) &&
    value >= 0
    ? value + 1
    : null;
}

export function mergeJobEvents(
  current: JobEvent[],
  incoming: JobEvent[],
): JobEvent[] {
  const byId = new Map(current.map((event) => [event.id, event]));
  incoming.forEach((event) => byId.set(event.id, event));
  return [...byId.values()].sort((left, right) => left.id - right.id);
}

export function QuizGenerationTimeline({
  events,
  loading = false,
}: {
  events: JobEvent[];
  loading?: boolean;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const [following, setFollowing] = useState(true);

  const scrollToLatest = () => {
    const node = viewport.current;
    if (node) node.scrollTop = node.scrollHeight;
    setFollowing(true);
  };

  useEffect(() => {
    const node = viewport.current;
    if (following && node) node.scrollTop = node.scrollHeight;
  }, [events.length, following]);

  return (
    <section className="mt-4 rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-black">Nhật ký tạo Quiz</h3>
        {!following && (
          <Button size="sm" variant="outline" onClick={scrollToLatest}>
            <ArrowDown className="mr-1 h-4 w-4" />
            Xem trạng thái mới nhất
          </Button>
        )}
      </div>
      <div
        ref={viewport}
        aria-live="polite"
        className="mt-3 h-80 space-y-2 overflow-y-auto rounded border bg-slate-950 p-3"
        onScroll={(event) => {
          const node = event.currentTarget;
          setFollowing(
            node.scrollHeight - node.scrollTop - node.clientHeight < 32,
          );
        }}
      >
        {events.map((event) => {
          const visibleLevel = isAiQualityWarningCode(event.code)
            ? "WARNING"
            : event.level;
          const Icon = icons[visibleLevel];
          const batchNumber = visibleIndex(event.batchIndex);
          const partNumber = visibleIndex(event.partIndex);
          const provider = event.provider
            ? (providerLabels[event.provider] ?? event.provider)
            : null;
          const accepted = metadataCount(event.metadata, "acceptedQuestions");
          const rejected = metadataCount(event.metadata, "rejectedQuestions");
          const failureDistribution = cognitiveFailureDistribution(event.metadata);
          const fieldErrors = validationErrors(event.metadata);
          const failureStage = metadataText(event.metadata, "stage");
          const diagnosticId = metadataText(event.metadata, "errorId");
          const semanticSameSource = metadataCount(
            event.metadata,
            "semanticSameSource",
          );
          const semanticCrossSource = metadataCount(
            event.metadata,
            "semanticCrossSource",
          );
          const droppedCitations = metadataCount(event.metadata, "dropped");
          const invalidCitations = metadataCount(
            event.metadata,
            "invalidCitations",
          );
          const semanticMatches =
            semanticSameSource !== null || semanticCrossSource !== null
              ? (semanticSameSource ?? 0) + (semanticCrossSource ?? 0)
              : null;
          return (
            <article
              key={event.id}
              className={`rounded border p-2 text-xs ${styles[visibleLevel]}`}
            >
              <div className="flex gap-2">
                <Icon className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap gap-x-2 font-bold">
                    <time dateTime={event.occurredAt}>
                      {new Date(event.occurredAt).toLocaleTimeString("vi-VN", {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </time>
                    {provider && <span>{provider}</span>}
                    {batchNumber !== null && (
                      <span>Nhóm {batchNumber}</span>
                    )}
                    {partNumber !== null && (
                      <span>Phần {partNumber}</span>
                    )}
                  </div>
                  <p className="mt-1 whitespace-pre-wrap">{event.message}</p>
                  {(accepted !== null || rejected !== null || failureDistribution.length > 0) && (
                    <div className="mt-2 rounded border border-current/20 bg-white/40 p-2">
                      <div className="flex flex-wrap gap-3 font-semibold">
                        {accepted !== null && <span>Đạt {accepted}</span>}
                        {rejected !== null && <span>Cần điều chỉnh {rejected}</span>}
                      </div>
                      {failureDistribution.length > 0 && (
                        <ul className="mt-1 list-inside list-disc space-y-0.5">
                          {failureDistribution.map(([reason, count]) => (
                            <li key={reason}>
                              {cognitiveReasonLabels[reason] ?? reason}: {count}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                  {(semanticMatches !== null ||
                    droppedCitations !== null ||
                    invalidCitations !== null) && (
                    <div className="mt-2 flex flex-wrap gap-3 rounded border border-current/20 bg-white/40 p-2 font-semibold">
                      {semanticMatches !== null && (
                        <span>Ánh xạ ngữ nghĩa {semanticMatches}</span>
                      )}
                      {droppedCitations !== null && (
                        <span>Bỏ citation phụ lỗi {droppedCitations}</span>
                      )}
                      {invalidCitations !== null && (
                        <span>Còn thiếu {invalidCitations} citation</span>
                      )}
                    </div>
                  )}
                  {fieldErrors.length > 0 && (
                    <ul className="mt-2 list-inside list-disc rounded border border-current/20 bg-white/40 p-2">
                      {fieldErrors.map((error) => (
                        <li key={`${error.field}:${error.type}`}>
                          <span className="font-semibold">{error.field}</span>
                          {`: ${validationMessage(error)}`}
                        </li>
                      ))}
                    </ul>
                  )}
                  {(failureStage || diagnosticId) && (
                    <p className="mt-1 opacity-75">
                      {failureStage ? `Giai đoạn: ${failureStage}` : ""}
                      {failureStage && diagnosticId ? " · " : ""}
                      {diagnosticId ? `Mã tra cứu: ${diagnosticId}` : ""}
                    </p>
                  )}
                  {(event.code || event.requestId) && (
                    <p className="mt-1 opacity-75">
                      {event.code}
                      {event.requestId
                        ? ` · Mã yêu cầu: ${event.requestId}`
                        : ""}
                    </p>
                  )}
                </div>
              </div>
            </article>
          );
        })}
        {!events.length && (
          <p className="text-sm text-slate-300">
            {loading
              ? "Đang tải nhật ký..."
              : "Chưa có trạng thái nào được ghi nhận."}
          </p>
        )}
      </div>
    </section>
  );
}
