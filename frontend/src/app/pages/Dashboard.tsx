import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bookmark,
  Compass,
  LayoutGrid,
  LogOut,
  Plus,
  Search,
  Settings,
  Trash2,
  UserRound,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "../../auth/AuthProvider";
import {
  bkquizApi,
  type Preferences,
  type PublicTopic,
  type Topic,
} from "../../api/bkquiz";
import { Badge, Button, Card, Checkbox, Input, Modal } from "../components/ui";
import { EmailVerificationAction } from "../components/EmailVerificationAction";

type View = "dashboard" | "explore" | "saved" | "settings" | "profile";
const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "Không thể tải dữ liệu.";
const errorTraceId = (error: unknown) => {
  if (!error || typeof error !== "object" || !("traceId" in error)) return null;
  const traceId = (error as { traceId?: unknown }).traceId;
  return typeof traceId === "string" && traceId ? traceId : null;
};
const date = (value: string | null | undefined) =>
  value
    ? new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium" }).format(
        new Date(value),
      )
    : "—";

export default function Dashboard() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user, logout, setCurrentUser, resendVerification } = useAuth();
  const [view, setView] = useState<View>("dashboard");
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [selectedPublicTopic, setSelectedPublicTopic] = useState<string | null>(
    null,
  );
  const [deleteTopic, setDeleteTopic] = useState<Topic | null>(null);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteAccountOpen, setDeleteAccountOpen] = useState(false);

  const topics = useQuery({
    queryKey: ["topics"],
    queryFn: () => bkquizApi.topics(),
  });
  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: bkquizApi.dashboard,
  });
  const profile = useQuery({
    queryKey: ["profile"],
    queryFn: bkquizApi.profile,
    enabled: view === "profile",
  });
  const preferences = useQuery({
    queryKey: ["preferences"],
    queryFn: bkquizApi.preferences,
    enabled: view === "settings",
  });
  const explore = useQuery({
    queryKey: ["explore", submittedQuery],
    queryFn: () => bkquizApi.explore(submittedQuery),
    enabled: view === "explore",
  });
  const saved = useQuery({
    queryKey: ["saved-topics"],
    queryFn: () => bkquizApi.savedTopics(),
    enabled: view === "saved" || view === "explore",
  });
  const detail = useQuery({
    queryKey: ["explore-topic", selectedPublicTopic],
    queryFn: () => bkquizApi.exploreTopic(selectedPublicTopic!),
    enabled: Boolean(selectedPublicTopic),
  });
  const savedIds = new Set(
    saved.data?.items.map((item) => item.topic.id) ?? [],
  );

  const deleteMutation = useMutation({
    mutationFn: bkquizApi.deleteTopic,
    onSuccess: async () => {
      setDeleteTopic(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["topics"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
      toast.success("Đã xóa chủ đề.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const bookmarkMutation = useMutation({
    mutationFn: async ({
      id,
      save,
    }: {
      id: string;
      save: boolean;
    }): Promise<void> => {
      if (save) await bkquizApi.saveTopic(id);
      else await bkquizApi.unsaveTopic(id);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["saved-topics"] }),
        queryClient.invalidateQueries({ queryKey: ["explore"] }),
        queryClient.invalidateQueries({ queryKey: ["explore-topic"] }),
      ]);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      navigate("/login", { replace: true });
    }
  };
  const loading = (
    <Card className="p-8 text-center text-[#6B7280]">Đang tải dữ liệu...</Card>
  );
  const failed = (error: unknown) => (
    <Card className="border-red-200 p-6 text-red-700">
      {errorMessage(error)}
    </Card>
  );

  const topicCard = (topic: Topic) => (
    <Card key={topic.id} className="group flex min-h-40 flex-col p-5">
      <div className="flex items-start justify-between gap-3">
        <Badge
          className={
            topic.status === "PUBLISHED"
              ? "bg-green-50 text-green-700"
              : "bg-amber-50 text-amber-700"
          }
        >
          {topic.status === "PUBLISHED" ? "Đã xuất bản" : "Bản nháp"}
        </Badge>
        <button
          aria-label="Xóa chủ đề"
          onClick={() => setDeleteTopic(topic)}
          className="text-[#9CA3AF] hover:text-red-600"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
      <Link className="mt-auto" to={`/workspace/${topic.id}`}>
        <h3 className="text-lg font-black hover:text-[#C8102E]">
          {topic.title}
        </h3>
        <p className="mt-2 line-clamp-2 text-sm text-[#6B7280]">
          {topic.description || "Chưa có mô tả"}
        </p>
        <p className="mt-3 text-xs text-[#9CA3AF]">
          Cập nhật {date(topic.updatedAt)}
        </p>
      </Link>
    </Card>
  );

  const publicCard = (topic: PublicTopic) => (
    <Card key={topic.id} className="flex flex-col p-5">
      <div className="flex justify-between gap-3">
        <Badge className="bg-[#FDE7EA] text-[#C8102E]">
          {topic.quizCount} quiz
        </Badge>
        <span className="text-xs text-[#6B7280]">
          {topic.learnerCount} người học
        </span>
      </div>
      <h3 className="mt-4 text-lg font-black">{topic.title}</h3>
      <p className="mt-2 line-clamp-2 text-sm text-[#6B7280]">
        {topic.description || "Không có mô tả"}
      </p>
      <p className="mt-3 text-xs">
        Bởi <b>{topic.ownerUsername}</b> · {topic.bookmarkCount} lượt lưu
      </p>
      <div className="mt-5 flex gap-2">
        <Button
          className="flex-1"
          onClick={() => setSelectedPublicTopic(topic.id)}
        >
          Xem chủ đề
        </Button>
        <Button
          variant="outline"
          aria-label={savedIds.has(topic.id) ? "Bỏ lưu" : "Lưu"}
          onClick={() =>
            bookmarkMutation.mutate({
              id: topic.id,
              save: !savedIds.has(topic.id),
            })
          }
        >
          <Bookmark
            className={`h-4 w-4 ${savedIds.has(topic.id) ? "fill-current" : ""}`}
          />
        </Button>
      </div>
    </Card>
  );

  const renderDashboard = () => {
    if (topics.isLoading) return loading;
    if (topics.error) return failed(topics.error);
    const items =
      topics.data?.items.filter((topic) =>
        topic.title.toLowerCase().includes(query.toLowerCase()),
      ) ?? [];
    return (
      <div className="space-y-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-black">Không gian học tập</h1>
            <p className="mt-1 text-[#6B7280]">
              Chào {user?.username}, dữ liệu dưới đây được đồng bộ từ BKQuiz.
            </p>
          </div>
          <Link to="/topic/new">
            <Button>
              <Plus className="h-4 w-4" />
              Tạo chủ đề
            </Button>
          </Link>
        </div>
        {dashboard.isLoading ? (
          <Card className="p-5 text-sm text-[#6B7280]">Đang tải thống kê...</Card>
        ) : dashboard.error ? (
          <Card className="border-red-200 p-5 text-red-700">
            <p>{errorMessage(dashboard.error)}</p>
            {errorTraceId(dashboard.error) && (
              <p className="mt-1 text-xs">Mã tra cứu: {errorTraceId(dashboard.error)}</p>
            )}
            <Button className="mt-3" size="sm" variant="outline" onClick={() => void dashboard.refetch()}>
              Thử lại
            </Button>
          </Card>
        ) : dashboard.data ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Chủ đề", dashboard.data.stats.topicCount],
              ["Quiz", dashboard.data.stats.quizCount],
              ["Lượt làm", dashboard.data.stats.submittedAttemptCount],
              ["Điểm trung bình", `${Number(dashboard.data.stats.averagePercentage).toFixed(1)}%`],
            ].map(([label, value]) => (
              <Card key={String(label)} className="p-5">
                <div className="text-3xl font-black">{value}</div>
                <div className="text-sm text-[#6B7280]">{label}</div>
              </Card>
            ))}
          </div>
        ) : null}
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Tìm chủ đề của bạn..."
        />
        {items.length ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {items.map(topicCard)}
          </div>
        ) : (
          <Card className="p-10 text-center">
            <h2 className="font-black">Chưa có chủ đề</h2>
            <p className="mt-2 text-sm text-[#6B7280]">
              Tạo chủ đề đầu tiên để thêm tài liệu và quiz.
            </p>
          </Card>
        )}
        <section>
          <h2 className="mb-3 text-xl font-black">Hoạt động gần đây</h2>
          {dashboard.error ? (
            <p className="text-sm text-[#6B7280]">Hoạt động tạm thời chưa tải được.</p>
          ) : dashboard.isLoading ? (
            <p className="text-sm text-[#6B7280]">Đang tải hoạt động...</p>
          ) : dashboard.data?.recentActivities.length ? (
            <div className="space-y-2">
              {dashboard.data.recentActivities.map((item) => (
                <Card key={item.attemptId} className="flex justify-between p-4">
                  <span>
                    Đã làm <b>{item.quizTitle}</b>
                  </span>
                  <span>
                    {item.percentage == null
                      ? item.status
                      : `${Number(item.percentage).toFixed(1)}%`}{" "}
                    · {date(item.occurredAt)}
                  </span>
                </Card>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[#6B7280]">Chưa có lượt làm bài nào.</p>
          )}
        </section>
      </div>
    );
  };

  const renderExplore = () => (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-black">Khám phá chủ đề</h1>
        <p className="mt-2 text-[#6B7280]">
          Chỉ hiển thị chủ đề và quiz đã được xuất bản công khai.
        </p>
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setSubmittedQuery(query);
        }}
      >
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Tìm chủ đề..."
        />
        <Button>
          <Search className="h-4 w-4" />
          Tìm
        </Button>
      </form>
      {explore.isLoading ? (
        loading
      ) : explore.error ? (
        failed(explore.error)
      ) : explore.data?.items.length ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {explore.data.items.map(publicCard)}
        </div>
      ) : (
        <Card className="p-10 text-center">
          Không tìm thấy chủ đề công khai.
        </Card>
      )}
    </div>
  );
  const renderSaved = () => (
    <div className="space-y-6">
      <h1 className="text-3xl font-black">Chủ đề đã lưu</h1>
      {saved.isLoading ? (
        loading
      ) : saved.error ? (
        failed(saved.error)
      ) : saved.data?.items.length ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {saved.data.items.map((item) => publicCard(item.topic))}
        </div>
      ) : (
        <Card className="p-10 text-center">Bạn chưa lưu chủ đề nào.</Card>
      )}
    </div>
  );

  const renderProfile = () => profile.isLoading ? loading : profile.error || !profile.data ? failed(profile.error) : (
    <ProfilePanel
      key={profile.data.id}
      data={profile.data}
      onSave={async (body) => {
        const next = await bkquizApi.updateProfile(body);
        setCurrentUser(next);
        await queryClient.invalidateQueries({ queryKey: ["profile"] });
        toast.success("Đã cập nhật hồ sơ.");
      }}
      onAvatar={async (file) => { const next = await bkquizApi.uploadAvatar(file); setCurrentUser(next); await queryClient.invalidateQueries({ queryKey: ["profile"] }); }}
      onDeleteAvatar={async () => { const next = await bkquizApi.deleteAvatar(); setCurrentUser(next); await queryClient.invalidateQueries({ queryKey: ["profile"] }); }}
      onChangeAccountType={async (targetRole, password) => { const payload = await bkquizApi.changeAccountType(targetRole, password); setCurrentUser(payload.user); await queryClient.invalidateQueries(); }}
      onResendVerification={resendVerification}
      onDelete={() => setDeleteAccountOpen(true)}
    />
  );
  const renderSettings = () =>
    preferences.isLoading ? (
      loading
    ) : preferences.error ? (
      failed(preferences.error)
    ) : preferences.data ? (
      <SettingsPanel
        initial={preferences.data}
        onSave={async (value) => {
          await bkquizApi.updatePreferences(value);
          await queryClient.invalidateQueries({ queryKey: ["preferences"] });
          toast.success("Đã lưu cài đặt.");
        }}
      />
    ) : null;

  const content =
    view === "dashboard"
      ? renderDashboard()
      : view === "explore"
        ? renderExplore()
        : view === "saved"
          ? renderSaved()
          : view === "profile"
            ? renderProfile()
            : renderSettings();
  return (
    <div className="min-h-screen bg-[#F7F7F8] text-[#111827]">
      <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b bg-white px-5">
        <Link to="/" className="text-xl font-black text-[#C8102E]">
          BKQuiz
        </Link>
        <button
          onClick={() => setView("profile")}
          className="flex items-center gap-2 font-bold"
        >
          <UserRound className="h-5 w-5" />
          {user?.username}
        </button>
      </header>
      <div className="mx-auto grid max-w-[1500px] md:grid-cols-[240px_1fr]">
        <aside className="border-r bg-white p-4 md:min-h-[calc(100vh-4rem)]">
          <Link to="/classrooms" className="mb-2 flex w-full items-center gap-3 rounded-md bg-[#111827] px-3 py-3 text-sm font-black text-white">
            <Users className="h-5 w-5" />
            Lớp học
          </Link>
          {[
            ["dashboard", "Tất cả chủ đề", LayoutGrid],
            ["explore", "Khám phá", Compass],
            ["saved", "Chủ đề đã lưu", Bookmark],
            ["settings", "Cài đặt", Settings],
            ["profile", "Hồ sơ", UserRound],
          ].map(([id, label, Icon]) => {
            const I = Icon as typeof LayoutGrid;
            return (
              <button
                key={String(id)}
                onClick={() => setView(id as View)}
                className={`mb-1 flex w-full items-center gap-3 rounded-md px-3 py-3 text-sm font-black ${view === id ? "bg-[#FDE7EA] text-[#C8102E]" : "text-[#6B7280] hover:bg-[#F7F7F8]"}`}
              >
                <I className="h-5 w-5" />
                {String(label)}
              </button>
            );
          })}
          <button
            onClick={handleLogout}
            className="mt-6 flex w-full items-center gap-3 px-3 py-3 text-sm font-black text-red-600"
          >
            <LogOut className="h-5 w-5" />
            Đăng xuất
          </button>
        </aside>
        <main className="min-w-0 p-5 md:p-8">{content}</main>
      </div>
      {deleteTopic && (
        <Modal title="Xóa chủ đề?" onClose={() => setDeleteTopic(null)}>
          <div className="p-5">
            <p>
              Chủ đề <b>{deleteTopic.title}</b> sẽ không còn hiển thị.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setDeleteTopic(null)}>
                Hủy
              </Button>
              <Button
                variant="danger"
                onClick={() => deleteMutation.mutate(deleteTopic.id)}
              >
                Xóa
              </Button>
            </div>
          </div>
        </Modal>
      )}
      {selectedPublicTopic && (
        <Modal
          title="Chi tiết chủ đề"
          onClose={() => setSelectedPublicTopic(null)}
          className="max-w-2xl"
        >
          <div className="max-h-[70vh] overflow-y-auto p-5">
            {detail.isLoading
              ? "Đang tải..."
              : detail.error
                ? errorMessage(detail.error)
                : detail.data && (
                    <>
                      <h2 className="text-xl font-black">
                        {detail.data.topic.title}
                      </h2>
                      <p className="mt-2 text-sm text-[#6B7280]">
                        {detail.data.topic.description || "Không có mô tả"}
                      </p>
                      <div className="mt-5 space-y-3">
                        {detail.data.quizzes.length ? (
                          detail.data.quizzes.map((quiz) => (
                            <Card
                              key={quiz.id}
                              className="flex items-center justify-between gap-3 p-4"
                            >
                              <div>
                                <b>{quiz.title}</b>
                                <p className="text-xs text-[#6B7280]">
                                  {quiz.questionCount} câu ·{" "}
                                  {quiz.durationMinutes} phút ·{" "}
                                  {quiz.difficulty}
                                </p>
                              </div>
                              <Link to={`/quiz/${quiz.id}/take`}>
                                <Button size="sm">Làm bài</Button>
                              </Link>
                            </Card>
                          ))
                        ) : (
                          <p>Chủ đề chưa có quiz công khai.</p>
                        )}
                      </div>
                    </>
                  )}
          </div>
        </Modal>
      )}
      {deleteAccountOpen && (
        <Modal
          title="Yêu cầu xóa tài khoản"
          onClose={() => setDeleteAccountOpen(false)}
        >
          <form
            className="p-5"
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await bkquizApi.requestDeletion(deletePassword);
                await logout();
                navigate("/login", { replace: true });
              } catch (error) {
                toast.error(errorMessage(error));
              }
            }}
          >
            <p className="mb-3 text-sm text-[#6B7280]">
              Nhập mật khẩu để xác nhận. Mọi phiên đăng nhập sẽ bị thu hồi.
            </p>
            <Input
              type="password"
              value={deletePassword}
              onChange={(e) => setDeletePassword(e.target.value)}
              required
            />
            <Button variant="danger" className="mt-4 w-full">
              Xác nhận xóa
            </Button>
          </form>
        </Modal>
      )}
    </div>
  );
}

function ProfilePanel({ data, onSave, onAvatar, onDeleteAvatar, onChangeAccountType, onResendVerification, onDelete }: {
  data: Awaited<ReturnType<typeof bkquizApi.profile>>;
  onSave: (body: { username: string; bio?: string }) => Promise<void>;
  onAvatar: (file: File) => Promise<void>;
  onDeleteAvatar: () => Promise<void>;
  onChangeAccountType: (targetRole: "STUDENT" | "TEACHER", password: string) => Promise<void>;
  onResendVerification: (email: string) => Promise<void>;
  onDelete: () => void;
}) {
  const [username, setUsername] = useState(data.username);
  const [bio, setBio] = useState(data.bio ?? "");
  const [saving, setSaving] = useState(false);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [rolePassword, setRolePassword] = useState("");
  const [roleBusy, setRoleBusy] = useState(false);
  return <div className="mx-auto max-w-2xl space-y-5">
    <h1 className="text-3xl font-black">Hồ sơ</h1>
    <Card className="space-y-4 p-5">
      <div className="flex flex-wrap items-center gap-4">
        {data.avatarUrl ? <img src={data.avatarUrl} alt="Ảnh đại diện" className="h-24 w-24 rounded-full border object-cover" /> : <div className="flex h-24 w-24 items-center justify-center rounded-full bg-gray-100"><UserRound /></div>}
        <div className="space-y-2 text-sm"><b>Ảnh JPEG, PNG hoặc WebP (tối đa 5 MB)</b><Input type="file" accept="image/jpeg,image/png,image/webp" disabled={avatarBusy} onChange={async e=>{const file=e.target.files?.[0];if(!file)return;if(file.size>5*1024*1024){toast.error("Ảnh không được vượt quá 5 MB.");return;}setAvatarBusy(true);try{await onAvatar(file);toast.success("Đã cập nhật ảnh đại diện.");}catch(error){toast.error(errorMessage(error));}finally{setAvatarBusy(false);e.target.value="";}}}/>{data.avatarUrl&&<Button size="sm" variant="outline" disabled={avatarBusy} onClick={async()=>{setAvatarBusy(true);try{await onDeleteAvatar();toast.success("Đã xóa ảnh.");}catch(error){toast.error(errorMessage(error));}finally{setAvatarBusy(false);}}}>Xóa ảnh</Button>}</div>
      </div>
      <label className="block text-sm font-black">Tên hiển thị<Input value={username} onChange={e=>setUsername(e.target.value)}/></label>
      <label className="block text-sm font-black">Tiểu sử<textarea className="mt-1 min-h-28 w-full rounded-md border p-3 font-normal" value={bio} onChange={e=>setBio(e.target.value)}/></label>
      <p className="text-sm text-gray-500">{data.email} · {data.role} · {data.emailVerified?"Đã xác minh email":"Chưa xác minh email"}</p>
      {!data.emailVerified && <EmailVerificationAction email={data.email} onResend={onResendVerification} />}
      <Button disabled={saving} onClick={async()=>{setSaving(true);try{await onSave({username,bio});toast.success("Đã lưu hồ sơ.");}catch(error){toast.error(errorMessage(error));}finally{setSaving(false);}}}>Lưu hồ sơ</Button>
    </Card>
    {data.role!=="ADMIN"&&<Card className="p-5"><h2 className="font-black">Loại tài khoản</h2><p className="mt-2 text-sm text-gray-500">Nâng cấp thành giáo viên cần email đã xác minh. Chuyển về sinh viên yêu cầu đã lưu trữ mọi lớp đang sở hữu.</p><Input className="mt-4" type="password" value={rolePassword} onChange={e=>setRolePassword(e.target.value)} placeholder="Mật khẩu xác nhận"/><Button className="mt-3" disabled={roleBusy||!rolePassword} onClick={async()=>{setRoleBusy(true);try{await onChangeAccountType(data.role==="TEACHER"?"STUDENT":"TEACHER",rolePassword);setRolePassword("");toast.success("Đã đổi loại tài khoản.");}catch(error){toast.error(errorMessage(error));}finally{setRoleBusy(false);}}}>{data.role==="TEACHER"?"Chuyển thành sinh viên":"Nâng cấp thành giáo viên"}</Button></Card>}
    <Card className="border-red-200 p-5"><h2 className="font-black text-red-700">Xóa tài khoản</h2><Button variant="danger" className="mt-3" onClick={onDelete}>Yêu cầu xóa</Button></Card>
  </div>;
}

function SettingsPanel({
  initial,
  onSave,
}: {
  initial: Awaited<ReturnType<typeof bkquizApi.preferences>>;
  onSave: (value: typeof initial) => Promise<void>;
}) {
  const [value, setValue] = useState(initial);
  const [saving, setSaving] = useState(false);
  const fields: Array<[keyof Preferences, string]> = [
    ["emailStudyReminders", "Email nhắc học"],
    ["publicProfile", "Hồ sơ công khai"],
    ["attemptAutosave", "Tự động lưu bài làm"],
  ];
  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <h1 className="text-3xl font-black">Cài đặt</h1>
      <Card className="space-y-5 p-5">
        {fields.map(([key, label]) => (
          <label key={key} className="flex items-center justify-between">
            <span className="font-bold">{label}</span>
            <Checkbox
              checked={value[key]}
              onChange={(e) =>
                setValue((current) => ({ ...current, [key]: e.target.checked }))
              }
            />
          </label>
        ))}
        <Button
          disabled={saving}
          onClick={async () => {
            setSaving(true);
            try {
              await onSave(value);
            } finally {
              setSaving(false);
            }
          }}
        >
          Lưu cài đặt
        </Button>
      </Card>
    </div>
  );
}
