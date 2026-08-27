import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Copy, RefreshCcw, Send, Square, Trash2, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  bkquizApi,
  type AttemptChatCitation,
  type AttemptChatMessage,
  type AttemptChatStreamEvent,
  type AttemptResult,
} from "../../api/bkquiz";
import { Button } from "../components/ui";
import { MathMarkdown } from "../components/MathMarkdown";
import { citationLocation } from "./citationLocation";

export interface PendingAttemptQuestion {
  nonce: number;
  snapshotId: string;
  questionNumber: number;
  message: string;
}

export function AttemptAiChatPanel({
  attemptId,
  questions,
  activeQuestion,
  pending,
  onConsumed,
  onClose,
}: {
  attemptId: string;
  questions: AttemptResult["questions"];
  activeQuestion: { snapshotId: string; questionNumber: number };
  pending: PendingAttemptQuestion | null;
  onConsumed: () => void;
  onClose: () => void;
}) {
  const history = useQuery({
    queryKey: ["attempt-ai-chat", attemptId],
    queryFn: () => bkquizApi.attemptChatHistory(attemptId),
  });
  const [messages, setMessages] = useState<AttemptChatMessage[]>([]);
  const [composer, setComposer] = useState("");
  const [streaming, setStreaming] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement | null>(null);
  const handledNonce = useRef<number | null>(null);
  const questionNumbers = useMemo(
    () => new Map(questions.map((item, index) => [item.snapshotId, index + 1])),
    [questions],
  );

  useEffect(() => {
    if (history.data) setMessages((current) => {
      const merged = new Map(history.data.items.map((item) => [item.id, item]));
      current.forEach((item) => merged.set(item.id, item));
      return [...merged.values()].sort((left, right) => left.createdAt.localeCompare(right.createdAt));
    });
  }, [history.data]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);
  useEffect(() => () => controller.current?.abort(), []);

  const consumeEvent = useCallback((event: AttemptChatStreamEvent, temporaryId: string) => {
    if (event.type === "MESSAGE_STARTED" && event.assistantMessageId) {
      setMessages((current) => current.map((item) =>
        item.id === temporaryId ? { ...item, id: event.assistantMessageId! } : item));
      return event.assistantMessageId;
    }
    setMessages((current) => current.map((item) => {
      const targetId = event.assistantMessageId || temporaryId;
      if (item.id !== targetId && item.id !== temporaryId) return item;
      if (event.type === "DELTA") return { ...item, id: targetId, content: item.content + (event.delta || "") };
      if (event.type === "SOURCES") return { ...item, id: targetId, citations: event.sources || [] };
      if (event.type === "COMPLETED") return { ...item, id: targetId, status: "COMPLETED" as const };
      if (event.type === "FAILED") return {
        ...item, id: targetId, status: "FAILED" as const,
        errorCode: event.errorCode || "AI_CHAT_FAILED",
        errorMessage: event.message || "Không thể hoàn tất phản hồi AI.",
      };
      if (event.type === "CANCELLED") return { ...item, id: targetId, status: "CANCELLED" as const };
      return item;
    }));
    return event.assistantMessageId;
  }, []);

  const send = useCallback(async (snapshotId: string, _questionNumber: number, text: string) => {
    const normalized = text.trim();
    if (normalized.length < 2 || streaming) return;
    const now = new Date().toISOString();
    const clientMessageId = crypto.randomUUID();
    const temporaryAssistantId = `pending-${clientMessageId}`;
    setMessages((current) => [...current,
      {
        id: clientMessageId, questionSnapshotId: snapshotId, role: "USER", status: "COMPLETED",
        content: normalized, model: null, errorCode: null, errorMessage: null,
        replyToMessageId: null, createdAt: now, completedAt: now, citations: [],
      },
      {
        id: temporaryAssistantId, questionSnapshotId: snapshotId, role: "ASSISTANT", status: "GENERATING",
        content: "", model: null, errorCode: null, errorMessage: null,
        replyToMessageId: clientMessageId, createdAt: now, completedAt: null, citations: [],
      },
    ]);
    const abort = new AbortController();
    controller.current = abort;
    setStreaming(true);
    try {
      await bkquizApi.streamAttemptChat(attemptId, {
        snapshotId, clientMessageId, message: normalized,
      }, abort.signal, (event) => consumeEvent(event, temporaryAssistantId));
    } catch (error) {
      const cancelled = abort.signal.aborted;
      setMessages((current) => current.map((item) => item.id === temporaryAssistantId
        ? { ...item, status: cancelled ? "CANCELLED" : "FAILED",
            errorMessage: cancelled ? "Bạn đã dừng phản hồi." : error instanceof Error ? error.message : "Mất kết nối AI." }
        : item));
    } finally {
      controller.current = null;
      setStreaming(false);
    }
  }, [attemptId, consumeEvent, streaming]);

  useEffect(() => {
    if (!pending || handledNonce.current === pending.nonce) return;
    handledNonce.current = pending.nonce;
    onConsumed();
    void send(pending.snapshotId, pending.questionNumber, pending.message);
  }, [pending, onConsumed, send]);

  const regenerate = async (message: AttemptChatMessage) => {
    if (streaming) return;
    const temporaryId = `pending-${crypto.randomUUID()}`;
    setMessages((current) => [...current, { ...message, id: temporaryId, content: "",
      status: "GENERATING", errorCode: null, errorMessage: null, citations: [], createdAt: new Date().toISOString() }]);
    const abort = new AbortController();
    controller.current = abort;
    setStreaming(true);
    try {
      await bkquizApi.regenerateAttemptChat(attemptId, message.id, abort.signal,
        (event) => consumeEvent(event, temporaryId));
    } catch (error) {
      setMessages((current) => current.map((item) => item.id === temporaryId
        ? { ...item, status: abort.signal.aborted ? "CANCELLED" : "FAILED",
            errorMessage: error instanceof Error ? error.message : "Không thể thử lại." } : item));
    } finally {
      controller.current = null;
      setStreaming(false);
    }
  };

  const clear = async () => {
    if (!confirm("Xóa toàn bộ hội thoại AI của lượt làm bài này?")) return;
    await bkquizApi.clearAttemptChat(attemptId);
    setMessages([]);
    toast.success("Đã xóa hội thoại AI.");
  };

  return (
    <>
      <button aria-label="Đóng trợ giảng AI" className="fixed inset-0 z-40 bg-black/30 md:hidden" onClick={onClose} />
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l bg-white shadow-2xl md:w-[420px]">
        <header className="flex items-center justify-between border-b p-4">
          <div><b className="text-lg">Trợ giảng AI</b><p className="text-xs text-gray-500">Hội thoại chung cho lượt làm bài</p></div>
          <div className="flex gap-1">
            <Button variant="outline" size="sm" onClick={() => void clear()} disabled={streaming} title="Xóa hội thoại"><Trash2 className="h-4 w-4" /></Button>
            <Button variant="outline" size="sm" onClick={onClose} title="Đóng"><X className="h-4 w-4" /></Button>
          </div>
        </header>
        <div className="flex-1 space-y-4 overflow-y-auto p-4" aria-live="polite">
          {history.isLoading && <p className="text-sm text-gray-500">Đang tải hội thoại...</p>}
          {!history.isLoading && messages.length === 0 && (
            <div className="rounded-xl bg-blue-50 p-4 text-sm text-blue-900">Chọn một câu hỏi và nhập điều bạn muốn AI giải thích.</div>
          )}
          {messages.map((item) => (
            <div key={item.id} className={item.role === "USER" ? "ml-10" : "mr-4"}>
              <div className="mb-1 text-xs text-gray-500">{item.role === "USER" ? "Bạn" : "BKQuiz AI"} · Câu {questionNumbers.get(item.questionSnapshotId) || "?"}</div>
              <div className={`rounded-2xl p-3 text-sm ${item.role === "USER" ? "bg-[#C8102E] text-white" : "bg-gray-100"}`}>
                {item.role === "ASSISTANT" ? <MathMarkdown normalizeLegacy>{item.content || (item.status === "GENERATING" ? "Đang suy nghĩ…" : "")}</MathMarkdown> : item.content}
                {item.errorMessage && <p className="mt-2 text-red-700">{item.errorMessage}</p>}
              </div>
              {item.role === "ASSISTANT" && item.citations.length > 0 && <ChatSources sources={item.citations} />}
              {item.role === "ASSISTANT" && item.content && (
                <div className="mt-1 flex gap-1">
                  <button className="rounded p-1 text-gray-500 hover:bg-gray-100" title="Sao chép" onClick={() => void navigator.clipboard.writeText(item.content)}><Copy className="h-4 w-4" /></button>
                  {item.status !== "GENERATING" && <button className="rounded p-1 text-gray-500 hover:bg-gray-100" title="Thử lại" onClick={() => void regenerate(item)}><RefreshCcw className="h-4 w-4" /></button>}
                </div>
              )}
            </div>
          ))}
          <div ref={bottom} />
        </div>
        <form className="border-t p-3" onSubmit={(event) => {
          event.preventDefault();
          const value = composer;
          setComposer("");
          void send(activeQuestion.snapshotId, activeQuestion.questionNumber, value);
        }}>
          <div className="mb-2 text-xs font-semibold text-gray-500">Đang hỏi về Câu {activeQuestion.questionNumber}</div>
          <textarea className="min-h-20 w-full resize-none rounded-xl border p-3 text-sm outline-none focus:border-[#C8102E]" maxLength={4000}
            value={composer} onChange={(event) => setComposer(event.target.value)} placeholder="Hỏi cách giải, yêu cầu ví dụ hoặc giải thích thêm…" disabled={streaming} />
          <div className="mt-2 flex justify-end">
            {streaming ? <Button type="button" variant="outline" onClick={() => controller.current?.abort()}><Square className="mr-2 h-4 w-4" />Dừng</Button>
              : <Button type="submit" disabled={composer.trim().length < 2}><Send className="mr-2 h-4 w-4" />Gửi</Button>}
          </div>
        </form>
      </aside>
    </>
  );
}

function ChatSources({ sources }: { sources: AttemptChatCitation[] }) {
  return <details className="mt-2 rounded border bg-white p-2 text-xs">
    <summary className="cursor-pointer font-semibold">Nguồn tham khảo ({sources.length})</summary>
    {sources.map((source, index) => <div key={`${source.sourceChunkId}-${index}`} className="mt-2 border-l-2 pl-2">
      <b>{source.filename} · {citationLocation(source)}</b>
      {source.heading && <span> · {source.heading}</span>}
      <MathMarkdown normalizeLegacy>{source.evidenceQuote}</MathMarkdown>
    </div>)}
  </details>;
}
