import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router";
import {
  FileText,
  Image as ImageIcon,
  Paperclip,
  Send,
  Settings,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { Client } from "@stomp/stompjs";
import {
  bkquizApi,
  type ClassroomAttachment,
  type ClassroomMessagesPage,
} from "../../api/bkquiz";
import { accessTokenStore } from "../../auth/accessToken";
import { useAuth } from "../../auth/AuthProvider";
import { Button, Card, Checkbox, Input } from "../components/ui";
import { SharedResourceCard } from "../components/SharedResourceCard";

type Tab = "feed" | "assignments" | "resources" | "members" | "settings";

function Attachment({
  classroomId,
  item,
}: {
  classroomId: string;
  item: ClassroomAttachment;
}) {
  const [url, setUrl] = useState(item.accessUrl ?? undefined);
  useEffect(() => {
    if (item.accessUrl) return;
    void bkquizApi
      .classroomAttachmentAccess(classroomId, item.id)
      .then((value) => setUrl(value.url))
      .catch(() => undefined);
  }, [classroomId, item.accessUrl, item.id]);
  const displayUrl = item.accessUrl ?? url;
  if (item.image)
    return (
      <a href={displayUrl} target="_blank" rel="noreferrer" className="block">
        {displayUrl ? (
          <img
            src={displayUrl}
            alt={item.name}
            className="mt-2 max-h-64 rounded-lg object-contain"
          />
        ) : (
          <span className="text-xs">Đang tải ảnh...</span>
        )}
      </a>
    );
  return (
    <a
      href={displayUrl}
      download={item.name}
      className="mt-2 flex items-center gap-2 rounded border p-3 text-sm"
    >
      <FileText className="h-4 w-4" />
      <span>
        {item.name} · {(item.sizeBytes / 1024).toFixed(1)} KB
      </span>
    </a>
  );
}

export default function ClassroomDetail() {
  const { classroomId = "" } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("feed");
  const [content, setContent] = useState("");
  const [files, setFiles] = useState<ClassroomAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const room = useQuery({
    queryKey: ["classroom", classroomId],
    queryFn: () => bkquizApi.classroom(classroomId),
  });
  const messages = useQuery({
    queryKey: ["classroom-messages", classroomId],
    queryFn: () => bkquizApi.classroomMessages(classroomId),
    refetchInterval: 3000,
  });
  const members = useQuery({
    queryKey: ["classroom-members", classroomId],
    queryFn: () => bkquizApi.classroomMembers(classroomId),
  });
  const assignments = useQuery({
    queryKey: ["classroom-assignments", classroomId],
    queryFn: () => bkquizApi.assignments(classroomId),
  });
  const shares = useQuery({
    queryKey: ["classroom-shares", classroomId],
    queryFn: () => bkquizApi.classroomTopicShares(classroomId),
  });
  const topics = useQuery({
    queryKey: ["topics-for-share"],
    queryFn: () => bkquizApi.topics(),
  });
  const quizQueries = useQueries({
    queries: (topics.data?.items ?? []).map((topic) => ({
      queryKey: ["quizzes-for-share", topic.id],
      queryFn: () => bkquizApi.quizzes(topic.id),
    })),
  });
  const quizzes = quizQueries.flatMap((query) => query.data?.items ?? []);
  const send = useMutation({
    mutationFn: () =>
      bkquizApi.sendClassroomMessage(classroomId, {
        content,
        attachmentIds: files.map((f) => f.id),
      }),
    onMutate: async () => {
      await queryClient.cancelQueries({
        queryKey: ["classroom-messages", classroomId],
      });
      const previous = queryClient.getQueryData<ClassroomMessagesPage>([
        "classroom-messages",
        classroomId,
      ]);
      if (user) {
        queryClient.setQueryData<ClassroomMessagesPage>(
          ["classroom-messages", classroomId],
          {
            items: [
              {
                id: `pending-${crypto.randomUUID()}`,
                classroomId,
                senderId: user.id,
                senderUsername: user.username,
                type: files.some((f) => f.image)
                  ? "IMAGE"
                  : files.length
                    ? "FILE"
                    : "TEXT",
                content,
                topicShareId: null,
                assignmentId: null,
                resourcePreview: null,
                attachments: files,
                editedAt: null,
                deletedAt: null,
                createdAt: new Date().toISOString(),
                version: 0,
              },
              ...(previous?.items ?? []),
            ],
            nextBefore: previous?.nextBefore ?? null,
            nextBeforeId: previous?.nextBeforeId ?? null,
            unreadCount: previous?.unreadCount ?? 0,
          },
        );
      }
      return { previous };
    },
    onSuccess: () => {
      setContent("");
      setFiles([]);
    },
    onError: (e: Error, _v, context) => {
      if (context?.previous)
        queryClient.setQueryData(
          ["classroom-messages", classroomId],
          context.previous,
        );
      toast.error(e.message);
    },
    onSettled: () =>
      queryClient.invalidateQueries({
        queryKey: ["classroom-messages", classroomId],
      }),
  });
  const ordered = useMemo(
    () => [...(messages.data?.items ?? [])].reverse(),
    [messages.data],
  );
  useEffect(() => {
    const token = accessTokenStore.get();
    if (!token) return;
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const client = new Client({
      brokerURL: `${protocol}://${location.host}/ws`,
      connectHeaders: { Authorization: `Bearer ${token}` },
      reconnectDelay: 1000,
      maxReconnectDelay: 30000,
      onConnect: () => {
        client.subscribe(`/topic/classrooms/${classroomId}`, () => {
          void queryClient.invalidateQueries({
            queryKey: ["classroom-messages", classroomId],
          });
        });
      },
    });
    client.activate();
    return () => {
      void client.deactivate();
    };
  }, [classroomId, queryClient]);
  useEffect(() => {
    if (messages.data) void bkquizApi.markClassroomRead(classroomId);
  }, [classroomId, messages.data]);
  const upload = async (list: FileList | null) => {
    if (!list) return;
    setUploading(true);
    try {
      for (const file of Array.from(list).slice(0, 10 - files.length)) {
        const attachment = await bkquizApi.uploadClassroomAttachment(
          classroomId,
          file,
        );
        setFiles((current) => [...current, attachment]);
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setUploading(false);
    }
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (content.trim() || files.length) send.mutate();
  };
  if (room.isLoading) return <main className="p-10">Đang tải lớp...</main>;
  if (room.error || !room.data)
    return (
      <main className="p-10 text-red-700">
        {(room.error as Error)?.message || "Không tìm thấy lớp."}
      </main>
    );
  const isManager =
    room.data.ownerId === user?.id ||
    members.data?.some(
      (m) =>
        m.userId === user?.id && (m.role === "OWNER" || m.role === "TEACHER"),
    );
  return (
    <div className="min-h-screen bg-[#F7F7F8]">
      <header className="border-b bg-white p-5">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div>
            <Link to="/classrooms" className="text-sm text-[#C8102E]">
              ← Các lớp học
            </Link>
            <h1 className="text-2xl font-black">{room.data.name}</h1>
          </div>
          <div className="text-sm">
            Mã lớp: <b>{room.data.joinCode}</b>
          </div>
        </div>
      </header>
      <div className="mx-auto max-w-7xl p-5">
        <nav className="mb-5 flex gap-2 overflow-x-auto">
          {(
            [
              ["feed", "Bảng tin"],
              ["assignments", "Bài tập & Quiz"],
              ["resources", "Tài nguyên"],
              ["members", "Thành viên"],
              ["settings", "Cài đặt"],
            ] as [Tab, string][]
          ).map(([id, label]) => (
            <Button
              key={id}
              variant={tab === id ? "primary" : "outline"}
              onClick={() => setTab(id)}
            >
              {label}
            </Button>
          ))}
        </nav>
        {tab === "feed" && (
          <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
            <Card className="overflow-hidden">
              <div className="max-h-[58vh] min-h-96 space-y-3 overflow-y-auto p-4">
                {messages.data?.nextBefore && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="mx-auto flex"
                    onClick={() =>
                      void bkquizApi
                        .classroomMessages(
                          classroomId,
                          messages.data?.nextBefore ?? undefined,
                          messages.data?.nextBeforeId ?? undefined,
                        )
                        .then((older) =>
                          queryClient.setQueryData<ClassroomMessagesPage>(
                            ["classroom-messages", classroomId],
                            (current) => ({
                              items: [
                                ...(current?.items ?? []),
                                ...older.items,
                              ],
                              nextBefore: older.nextBefore,
                              nextBeforeId: older.nextBeforeId,
                              unreadCount: current?.unreadCount ?? 0,
                            }),
                          ),
                        )
                    }
                  >
                    Tải tin nhắn cũ hơn
                  </Button>
                )}
                {ordered.length ? (
                  ordered.map((message) => (
                    <div
                      key={message.id}
                      className={`max-w-[85%] rounded-lg p-3 ${message.senderId === user?.id ? "ml-auto bg-[#FDE7EA]" : "bg-[#F7F7F8]"}`}
                    >
                      <div className="text-xs font-black">
                        {message.senderUsername}
                      </div>
                      {message.deletedAt ? (
                        <i className="text-xs">Tin nhắn đã xóa</i>
                      ) : (
                        <>
                          {message.content &&
                            !(
                              message.type === "QUIZ_SHARE" &&
                              message.content === message.resourcePreview?.title
                            ) && (
                            <p className="whitespace-pre-wrap text-sm">
                              {message.content}
                            </p>
                          )}
                          {(message.type === "TOPIC_SHARE" ||
                            message.type === "QUIZ_SHARE") &&
                            message.resourcePreview && (
                              <SharedResourceCard
                                classroomId={classroomId}
                                preview={message.resourcePreview}
                              />
                            )}
                          {message.attachments.map((a) => (
                            <Attachment
                              key={a.id}
                              classroomId={classroomId}
                              item={a}
                            />
                          ))}
                        </>
                      )}
                      <time className="mt-1 block text-[10px] text-[#6B7280]">
                        {new Date(message.createdAt).toLocaleString("vi-VN")}
                        {message.editedAt ? " · đã sửa" : ""}
                      </time>
                      {!message.deletedAt &&
                        !message.id.startsWith("pending-") &&
                        (message.senderId === user?.id || isManager) && (
                          <div className="mt-1 flex gap-2 text-[11px]">
                            {message.senderId === user?.id &&
                              message.content && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    const next = window.prompt(
                                      "Sửa tin nhắn",
                                      message.content ?? "",
                                    );
                                    if (next)
                                      void bkquizApi
                                        .editClassroomMessage(
                                          classroomId,
                                          message.id,
                                          next,
                                        )
                                        .then(() =>
                                          queryClient.invalidateQueries({
                                            queryKey: [
                                              "classroom-messages",
                                              classroomId,
                                            ],
                                          }),
                                        )
                                        .catch((e) => toast.error(e.message));
                                  }}
                                >
                                  Sửa
                                </button>
                              )}
                            <button
                              type="button"
                              className="text-red-600"
                              onClick={() =>
                                void bkquizApi
                                  .deleteClassroomMessage(
                                    classroomId,
                                    message.id,
                                  )
                                  .then(() =>
                                    queryClient.invalidateQueries({
                                      queryKey: [
                                        "classroom-messages",
                                        classroomId,
                                      ],
                                    }),
                                  )
                                  .catch((e) => toast.error(e.message))
                              }
                            >
                              Xóa
                            </button>
                          </div>
                        )}
                    </div>
                  ))
                ) : (
                  <p className="text-center text-sm text-[#6B7280]">
                    Chưa có tin nhắn.
                  </p>
                )}
              </div>
              <form onSubmit={submit} className="border-t p-3">
                <div className="mb-2 flex flex-wrap gap-2">
                  {files.map((f) => (
                    <span
                      key={f.id}
                      className="rounded bg-[#F7F7F8] px-2 py-1 text-xs"
                    >
                      {f.image ? (
                        <ImageIcon className="mr-1 inline h-3 w-3" />
                      ) : (
                        <FileText className="mr-1 inline h-3 w-3" />
                      )}
                      {f.name}
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <label className="flex h-10 cursor-pointer items-center rounded border px-3">
                    <Paperclip className="h-4 w-4" />
                    <input
                      className="hidden"
                      type="file"
                      multiple
                      disabled={uploading || room.data.status === "ARCHIVED"}
                      onChange={(e) => void upload(e.target.files)}
                    />
                  </label>
                  <Input
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    placeholder="Nhập tin nhắn..."
                    disabled={room.data.status === "ARCHIVED"}
                    maxLength={10000}
                  />
                  <Button
                    disabled={
                      send.isPending ||
                      uploading ||
                      room.data.status === "ARCHIVED"
                    }
                  >
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              </form>
            </Card>
            <Card className="p-5">
              <h2 className="font-black">Thông tin lớp</h2>
              <p className="mt-2 text-sm text-[#6B7280]">
                {room.data.description || "Chưa có mô tả"}
              </p>
              <p className="mt-4 text-sm">
                <Users className="mr-1 inline h-4 w-4" />
                {members.data?.length ?? 0} thành viên
              </p>
            </Card>
          </div>
        )}
        {tab === "assignments" && (
          <Assignments
            classroomId={classroomId}
            items={assignments.data?.items ?? []}
            quizzes={quizzes}
            canCreate={Boolean(user?.emailVerified)}
          />
        )}
        {tab === "resources" && (
          <Card className="p-5">
            <h2 className="font-black">Chia sẻ chủ đề</h2>
            <div className="mt-4 flex flex-wrap gap-2">
              {topics.data?.items.map((t) => (
                <Button
                  key={t.id}
                  variant="outline"
                  disabled={!user?.emailVerified}
                  onClick={() =>
                    void bkquizApi
                      .shareTopic(classroomId, t.id)
                      .then(async () => {
                        await Promise.all([
                          queryClient.invalidateQueries({
                            queryKey: ["classroom-shares", classroomId],
                          }),
                          queryClient.invalidateQueries({
                            queryKey: ["classroom-messages", classroomId],
                          }),
                        ]);
                      })
                      .catch((e) => toast.error(e.message))
                  }
                >
                  {t.title}
                </Button>
              ))}
            </div>
            <div className="mt-6 space-y-2">
              {shares.data?.map((share) => (
                <SharedResourceCard
                  key={share.id}
                  classroomId={classroomId}
                  preview={share.resourcePreview}
                />
              ))}
            </div>
          </Card>
        )}
        {tab === "members" && (
          <Card className="divide-y">
            {members.data?.map((m) => (
              <div key={m.id} className="flex items-center justify-between p-4">
                <span>
                  <b>{m.username}</b>
                </span>
                <div className="flex items-center gap-2">
                  <span className="text-sm">{m.role}</span>
                  {room.data.ownerId === user?.id && m.userId !== user.id && (
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() =>
                        void bkquizApi
                          .removeClassroomMember(classroomId, m.userId)
                          .then(() =>
                            queryClient.invalidateQueries({
                              queryKey: ["classroom-members", classroomId],
                            }),
                          )
                          .catch((e) => toast.error(e.message))
                      }
                    >
                      Xóa
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </Card>
        )}
        {tab === "settings" && (
          <Card className="max-w-2xl space-y-4 p-5">
            <h2 className="flex items-center gap-2 font-black">
              <Settings className="h-4 w-4" />
              Cài đặt lớp
            </h2>
            {isManager ? (
              <>
                <label className="flex items-center justify-between">
                  <span>Cho phép tham gia bằng mã</span>
                  <Checkbox
                    checked={room.data.joinEnabled}
                    onChange={(e) =>
                      void bkquizApi
                        .updateJoinSettings(classroomId, e.target.checked)
                        .then(() =>
                          queryClient.invalidateQueries({
                            queryKey: ["classroom", classroomId],
                          }),
                        )
                    }
                  />
                </label>
                <Button
                  variant="outline"
                  onClick={() =>
                    void navigator.clipboard
                      .writeText(
                        `${location.origin}/join-class/${room.data.joinCode}`,
                      )
                      .then(() => toast.success("Đã sao chép link tham gia."))
                  }
                >
                  Sao chép link tham gia
                </Button>
                <Button
                  variant="outline"
                  onClick={() =>
                    void bkquizApi.rotateJoinCode(classroomId).then(() =>
                      queryClient.invalidateQueries({
                        queryKey: ["classroom", classroomId],
                      }),
                    )
                  }
                >
                  Đổi mã tham gia
                </Button>
                <Button
                  variant="danger"
                  onClick={() =>
                    void bkquizApi.archiveClassroom(classroomId).then(() =>
                      queryClient.invalidateQueries({
                        queryKey: ["classroom", classroomId],
                      }),
                    )
                  }
                >
                  Lưu trữ lớp
                </Button>
              </>
            ) : (
              <p>Bạn không có quyền thay đổi cài đặt lớp.</p>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}

function Assignments({
  classroomId,
  items,
  quizzes,
  canCreate,
}: {
  classroomId: string;
  items: Awaited<ReturnType<typeof bkquizApi.assignments>>["items"];
  quizzes: { id: string; title: string; durationMinutes: number }[];
  canCreate: boolean;
}) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [quizId, setQuizId] = useState("");
  const [title, setTitle] = useState("");
  const [duration, setDuration] = useState(30);
  const [attempts, setAttempts] = useState(1);
  const [showScore, setShowScore] = useState(true);
  const [allowReview, setAllowReview] = useState(true);
  const [shuffleQuestions, setShuffleQuestions] = useState(false);
  const [shuffleOptions, setShuffleOptions] = useState(false);
  const [showLeaderboard, setShowLeaderboard] = useState(false);
  const [opensAt, setOpensAt] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [submissionAssignmentId, setSubmissionAssignmentId] =
    useState<string>();
  const submissions = useQuery({
    queryKey: ["assignment-submissions", submissionAssignmentId],
    queryFn: () => bkquizApi.assignmentSubmissions(submissionAssignmentId!),
    enabled: Boolean(submissionAssignmentId),
  });
  const [policy, setPolicy] = useState<
    "IMMEDIATE" | "AFTER_DUE_DATE" | "NEVER"
  >("IMMEDIATE");
  const create = useMutation({
    mutationFn: () =>
      bkquizApi.createAssignment(classroomId, {
        quizId,
        title,
        instructions: null,
        opensAt: opensAt ? new Date(opensAt).toISOString() : null,
        dueAt: dueAt ? new Date(dueAt).toISOString() : null,
        durationMinutes: duration,
        maxAttempts: attempts,
        answerReleasePolicy: policy,
        showScore,
        allowReview,
        shuffleQuestions,
        shuffleOptions,
        showLeaderboard,
      }),
    onSuccess: async (a) => {
      await bkquizApi.publishAssignment(a.id);
      await Promise.all([
        client.invalidateQueries({
          queryKey: ["classroom-assignments", classroomId],
        }),
        client.invalidateQueries({
          queryKey: ["classroom-messages", classroomId],
        }),
        client.invalidateQueries({
          queryKey: ["classroom-shared-resource", classroomId],
        }),
      ]);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <div className="grid gap-5 lg:grid-cols-[360px_1fr]">
      <Card className="space-y-3 p-5">
        <h2 className="font-black">Chia sẻ / giao Quiz</h2>
        <select
          className="h-10 w-full rounded border px-3"
          value={quizId}
          onChange={(e) => {
            setQuizId(e.target.value);
            const selected = quizzes.find((q) => q.id === e.target.value);
            setTitle(selected?.title ?? "");
            if (selected) setDuration(selected.durationMinutes);
          }}
        >
          <option value="">Chọn quiz...</option>
          {quizzes.map((q) => (
            <option key={q.id} value={q.id}>
              {q.title}
            </option>
          ))}
        </select>
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Tiêu đề"
        />
        <div className="grid grid-cols-2 gap-2">
          <Input
            type="number"
            min={1}
            max={1440}
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
          />
          <Input
            type="number"
            min={1}
            max={100}
            value={attempts}
            onChange={(e) => setAttempts(Number(e.target.value))}
          />
        </div>
        <label className="block text-xs font-bold">
          Mở từ
          <Input
            type="datetime-local"
            value={opensAt}
            onChange={(e) => setOpensAt(e.target.value)}
          />
        </label>
        <label className="block text-xs font-bold">
          Hạn làm
          <Input
            type="datetime-local"
            value={dueAt}
            onChange={(e) => setDueAt(e.target.value)}
          />
        </label>
        <select
          className="h-10 w-full rounded border px-3"
          value={policy}
          onChange={(e) => setPolicy(e.target.value as typeof policy)}
        >
          <option value="IMMEDIATE">Đáp án ngay</option>
          <option value="AFTER_DUE_DATE">Sau hạn</option>
          <option value="NEVER">Không công bố</option>
        </select>
        {[
          [showScore, setShowScore, "Hiện điểm"],
          [allowReview, setAllowReview, "Cho review"],
          [shuffleQuestions, setShuffleQuestions, "Xáo câu hỏi"],
          [shuffleOptions, setShuffleOptions, "Xáo lựa chọn"],
          [showLeaderboard, setShowLeaderboard, "Hiện bảng xếp hạng"],
        ].map(([value, setValue, label]) => (
          <label key={String(label)} className="flex gap-2 text-sm">
            <Checkbox
              checked={value as boolean}
              onChange={(e) =>
                (setValue as (v: boolean) => void)(e.target.checked)
              }
            />
            {String(label)}
          </label>
        ))}
        <Button
          disabled={!canCreate || !quizId || !title || create.isPending}
          onClick={() => create.mutate()}
        >
          Giao Quiz
        </Button>
      </Card>
      <div className="space-y-3">
        {items.length ? (
          items.map((a) => (
            <Card key={a.id} className="p-5">
              <div className="flex justify-between">
                <h3 className="font-black">{a.title}</h3>
                <span className="text-xs">{a.status}</span>
              </div>
              <p className="mt-2 text-sm">
                {a.maxAttempts} lượt · {a.durationMinutes} phút ·{" "}
                {a.showScore ? "Hiện điểm" : "Ẩn điểm"}
              </p>
              {a.status === "PUBLISHED" && (
                <div className="mt-3 flex gap-2">
                  <Button
                    size="sm"
                    onClick={() =>
                      void bkquizApi
                        .startAttempt(a.quizId, a.id)
                        .then((attempt) => navigate(`/attempt/${attempt.id}`))
                        .catch((e) => toast.error(e.message))
                    }
                  >
                    Làm bài
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setSubmissionAssignmentId(a.id)}
                  >
                    Xem bài nộp
                  </Button>
                </div>
              )}
            </Card>
          ))
        ) : (
          <Card className="p-8 text-center">
            Chưa có bài tập hoặc Quiz được chia sẻ.
          </Card>
        )}
      </div>
      {submissionAssignmentId && (
        <Card className="p-5 lg:col-span-2">
          <div className="flex justify-between">
            <h3 className="font-black">Bài nộp</h3>
            <button onClick={() => setSubmissionAssignmentId(undefined)}>
              Đóng
            </button>
          </div>
          {submissions.isLoading ? (
            <p>Đang tải...</p>
          ) : submissions.error ? (
            <p className="text-red-700">
              {(submissions.error as Error).message}
            </p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr>
                    <th>Người dùng</th>
                    <th>Lần làm</th>
                    <th>Điểm</th>
                    <th>Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {submissions.data?.items.map((row) => (
                    <tr key={row.attemptId} className="border-t">
                        <td className="py-2">{row.username}</td>
                      <td>{row.attemptNumber}</td>
                      <td>
                        {row.percentage == null ? "—" : `${row.percentage}%`}
                      </td>
                      <td>{row.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
