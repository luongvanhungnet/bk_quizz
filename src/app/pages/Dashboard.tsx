import { useMemo, useState } from "react";
import { Link } from "react-router";
import {
  Bell,
  BookOpen,
  Bookmark,
  ChevronRight,
  Clock3,
  Compass,
  FileQuestion,
  LayoutGrid,
  LogOut,
  MoreVertical,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Star,
  Trash2,
  UserRound,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, Card, Input, Modal } from "../components/ui";
import { activities, communityTopics, stats, topics } from "../data/mock";

type View = "dashboard" | "explore" | "settings" | "profile" | "saved";

export default function Dashboard() {
  const [view, setView] = useState<View>("dashboard");
  const [query, setQuery] = useState("");
  const [recentOpen, setRecentOpen] = useState(false);
  const [savedTopic, setSavedTopic] = useState<(typeof communityTopics)[number] | null>(null);
  const [deleteTopic, setDeleteTopic] = useState<(typeof topics)[number] | null>(null);

  const filteredTopics = useMemo(() => {
    const search = query.trim().toLowerCase();
    if (!search) return topics;
    return topics.filter((topic) => `${topic.name} ${topic.subject}`.toLowerCase().includes(search));
  }, [query]);

  const navItems = [
    { id: "dashboard" as const, label: "Tất cả chủ đề", icon: LayoutGrid },
    { id: "explore" as const, label: "Khám phá", icon: Compass },
    { id: "saved" as const, label: "Chủ đề đã lưu", icon: Bookmark },
    { id: "settings" as const, label: "Cài đặt", icon: Settings },
  ];

  const TopicCard = ({ topic, featured = false }: { topic: (typeof topics)[number]; featured?: boolean }) => {
    const Icon = topic.icon;
    return (
      <Card className={`group relative flex min-h-[150px] flex-col p-5 transition hover:-translate-y-0.5 hover:border-[#C8102E]/45 hover:shadow-md ${featured ? "border-t-4 border-t-[#C8102E]" : ""}`}>
        <div className="flex items-start justify-between">
          <div className={`flex h-11 w-11 items-center justify-center rounded-md ${topic.color}`}>
            <Icon className="h-5 w-5" />
          </div>
          <button
            className="rounded-md p-1.5 text-[#9CA3AF] opacity-100 hover:bg-[#F7F7F8] hover:text-[#111827] md:opacity-0 md:group-hover:opacity-100"
            onClick={(event) => {
              event.preventDefault();
              setDeleteTopic(topic);
            }}
            aria-label="Mở menu chủ đề"
          >
            <MoreVertical className="h-5 w-5" />
          </button>
        </div>
        <Link to={`/workspace/${topic.id}`} className="mt-auto block">
          <h3 className="text-lg font-black text-[#111827] transition group-hover:text-[#C8102E]">{topic.name}</h3>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs font-semibold text-[#6B7280]">
            <span>{topic.subject}</span>
            <span className="h-1 w-1 rounded-full bg-[#D1D5DB]" />
            <span>{topic.quizCount} quiz</span>
            <span className="h-1 w-1 rounded-full bg-[#D1D5DB]" />
            <span>Đã mở {topic.updated}</span>
          </div>
        </Link>
        {featured && (
          <Badge className="absolute right-5 top-5 bg-[#FDE7EA] text-[#C8102E]">Nổi bật</Badge>
        )}
      </Card>
    );
  };

  const renderDashboard = () => (
    <div className="space-y-10">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div>
          <h1 className="text-3xl font-black">Không gian học tập</h1>
          <p className="mt-2 text-[#6B7280]">Chào mừng bạn quay lại, tiếp tục ôn tập nhé.</p>
        </div>
        <Link to="/topic/new">
          <Button variant="outline" className="bg-white">
            <Plus className="h-4 w-4" />
            Tạo chủ đề mới
          </Button>
        </Link>
      </div>

      <section>
        <div className="mb-4 flex items-center gap-2">
          <Zap className="h-5 w-5 fill-[#C8102E] text-[#C8102E]" />
          <h2 className="text-xl font-black">Chủ đề nổi bật</h2>
        </div>
        <div className="flex gap-4 overflow-x-auto pb-3 hide-scrollbar">
          {filteredTopics.filter((topic) => topic.featured).map((topic) => (
            <div key={topic.id} className="min-w-[280px] flex-1">
              <TopicCard topic={topic} featured />
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock3 className="h-5 w-5 text-[#6B7280]" />
            <h2 className="text-xl font-black">Gần đây</h2>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setRecentOpen(true)}>
            Xem nhanh
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <Link to="/topic/new">
            <Card className="flex min-h-[160px] flex-col items-center justify-center border-dashed bg-white/70 p-5 text-center transition hover:border-[#C8102E] hover:bg-[#FFF8E8]">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[#F7F7F8] text-[#6B7280]">
                <Plus className="h-5 w-5" />
              </div>
              <h3 className="font-black">Tạo chủ đề mới</h3>
              <p className="mt-1 text-xs font-semibold text-[#9CA3AF]">Từ tài liệu môn học</p>
            </Card>
          </Link>
          {filteredTopics.map((topic) => (
            <TopicCard key={topic.id} topic={topic} />
          ))}
        </div>
      </section>
    </div>
  );

  const renderExplore = () => (
    <div>
      <div className="mx-auto mb-8 max-w-2xl text-center">
        <h1 className="text-3xl font-black">Khám phá chủ đề</h1>
        <p className="mt-3 text-[#6B7280]">Xem và lưu các bộ quiz được cộng đồng sinh viên Bách Khoa chia sẻ.</p>
      </div>
      <div className="mx-auto mb-8 flex max-w-2xl gap-2 rounded-lg border border-[#E5E7EB] bg-white p-2 shadow-sm">
        <Input className="border-0 focus-visible:ring-0" placeholder="Tìm theo môn học, mã học phần..." />
        <Button onClick={() => toast.info("Đã lọc chủ đề cộng đồng ở chế độ demo.")}>Tìm</Button>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {communityTopics.map((topic) => (
          <Card key={topic.id} className="flex flex-col overflow-hidden transition hover:-translate-y-0.5 hover:shadow-md">
            <div className="p-5">
              <div className="mb-4 flex items-center justify-between">
                <Badge className="bg-[#FDE7EA] text-[#C8102E]">{topic.subject}</Badge>
                <span className="flex items-center gap-1 text-sm font-black text-[#F59E0B]">
                  <Star className="h-4 w-4 fill-current" />
                  {topic.rating}
                </span>
              </div>
              <h3 className="text-lg font-black leading-tight">{topic.title}</h3>
              <p className="mt-2 text-sm text-[#6B7280]">Bởi <b>{topic.author}</b></p>
              <div className="mt-4 grid grid-cols-2 gap-3 border-y border-[#F3F4F6] py-3 text-sm">
                <span><b>{topic.quizzes}</b> quiz</span>
                <span><b>{topic.learners}</b> người ôn</span>
              </div>
            </div>
            <div className="mt-auto flex gap-2 border-t border-[#E5E7EB] bg-[#F9FAFB] p-4">
              <Button className="flex-1" onClick={() => setSavedTopic(topic)}>Xem chủ đề</Button>
              <Button
                variant="outline"
                onClick={() => toast.success(`Đã lưu ${topic.title}`)}
              >
                <Bookmark className="h-4 w-4" />
                {topic.saves}
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );

  const renderSettings = () => (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-8 text-3xl font-black">Cài đặt</h1>
      <div className="space-y-5">
        {[
          ["Thông báo nhắc ôn tập", "Nhận email khi gần tới lịch kiểm tra.", true],
          ["Hiển thị hồ sơ công khai", "Cho phép cộng đồng xem chủ đề đã chia sẻ.", false],
          ["Tự động lưu khi làm bài", "Lưu đáp án sau mỗi lựa chọn.", true],
        ].map(([title, desc, enabled]) => (
          <Card key={String(title)} className="flex items-center justify-between gap-4 p-5">
            <div>
              <h3 className="font-black">{title}</h3>
              <p className="mt-1 text-sm text-[#6B7280]">{desc}</p>
            </div>
            <button
              className={`relative h-6 w-11 rounded-full transition ${enabled ? "bg-[#C8102E]" : "bg-[#D1D5DB]"}`}
              onClick={() => toast.success("Đã lưu cài đặt demo.")}
              aria-label="Bật tắt cài đặt"
            >
              <span className={`absolute top-1 h-4 w-4 rounded-full bg-white shadow transition ${enabled ? "left-6" : "left-1"}`} />
            </button>
          </Card>
        ))}
        <Card className="p-5">
          <h3 className="font-black text-[#DC2626]">Xóa tài khoản</h3>
          <p className="mt-1 text-sm text-[#6B7280]">Thao tác nguy hiểm này chỉ hiển thị dưới dạng demo.</p>
          <Button className="mt-4" variant="danger" onClick={() => toast.error("Không thể xóa tài khoản trong bản demo.")}>
            Xóa tài khoản
          </Button>
        </Card>
      </div>
    </div>
  );

  const renderProfile = () => (
    <div className="mx-auto max-w-5xl">
      <Card className="mb-6 overflow-hidden">
        <div className="h-28 bg-[#111111] bk-soft-grid" />
        <div className="flex flex-col gap-5 px-6 pb-6 md:flex-row md:items-end md:justify-between">
          <div className="-mt-10 flex items-end gap-4">
            <div className="flex h-24 w-24 items-center justify-center rounded-full border-4 border-white bg-[#C8102E] text-2xl font-black text-white shadow-lg">
              SV
            </div>
            <div className="pb-2">
              <h1 className="text-2xl font-black">Sinh viên BK</h1>
              <p className="text-sm text-[#6B7280]">Viện Công nghệ Thông tin & Truyền thông</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => toast.info("Mở form chỉnh sửa hồ sơ demo.")}>Chỉnh sửa hồ sơ</Button>
            <Link to="/login">
              <Button variant="ghost">
                <LogOut className="h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </Card>

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((item) => (
          <Card key={item.label} className="p-5">
            <item.icon className="mb-4 h-5 w-5 text-[#C8102E]" />
            <div className="text-2xl font-black">{item.value}</div>
            <div className="mt-1 text-sm font-semibold text-[#6B7280]">{item.label}</div>
          </Card>
        ))}
      </div>

      <Card className="p-5">
        <h2 className="mb-4 text-xl font-black">Hoạt động gần đây</h2>
        <div className="space-y-3">
          {activities.map((item) => (
            <div key={item.title} className="flex items-center justify-between rounded-md border border-[#E5E7EB] p-3">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-md bg-[#FDE7EA] text-[#C8102E]">
                  <item.icon className="h-4 w-4" />
                </div>
                <div>
                  <p className="font-bold">{item.title}</p>
                  <p className="text-xs text-[#6B7280]">{item.time}</p>
                </div>
              </div>
              <span className="font-black text-[#C8102E]">{item.score}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );

  const renderSaved = () => (
    <div>
      <div className="mb-8 flex items-center gap-3">
        <Bookmark className="h-8 w-8 text-[#C8102E]" />
        <div>
          <h1 className="text-3xl font-black">Chủ đề đã lưu</h1>
          <p className="mt-1 text-[#6B7280]">Các bộ quiz cộng đồng bạn muốn ôn sau.</p>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {communityTopics.slice(0, 3).map((topic) => (
          <Card key={topic.id} className="cursor-pointer p-5 transition hover:border-[#C8102E]/45 hover:shadow-md" onClick={() => setSavedTopic(topic)}>
            <Badge className="mb-4 bg-[#FDE7EA] text-[#C8102E]">{topic.subject}</Badge>
            <h3 className="text-lg font-black">{topic.title}</h3>
            <p className="mt-2 text-sm text-[#6B7280]">Bởi {topic.author}</p>
            <Button className="mt-5 w-full">
              <FileQuestion className="h-4 w-4" />
              Học ngay
            </Button>
          </Card>
        ))}
      </div>
    </div>
  );

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#F7F7F8] font-sans text-[#111827]">
      <header className="z-20 flex h-16 shrink-0 items-center justify-between border-b border-[#E5E7EB] bg-white px-4 md:px-6">
        <Link to="/" className="flex w-48 items-center gap-2 text-xl font-black text-[#C8102E]">
          <Zap className="h-6 w-6 fill-current" />
          BKQuiz
        </Link>
        <div className="relative hidden max-w-2xl flex-1 md:block">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9CA3AF]" />
          <Input
            className="border-transparent bg-[#F7F7F8] pl-9"
            placeholder="Tìm chủ đề / môn học..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <div className="flex items-center gap-2 md:gap-3">
          <Button className="hidden sm:flex" onClick={() => setView("explore")}>
            <Compass className="h-4 w-4" />
            Khám phá
          </Button>
          <button className="rounded-md p-2 text-[#6B7280] hover:bg-[#F7F7F8]" onClick={() => toast.info("Không có thông báo mới.")}>
            <Bell className="h-5 w-5" />
          </button>
          <button className="rounded-md p-2 text-[#6B7280] hover:bg-[#F7F7F8]" onClick={() => setView("profile")}>
            <UserRound className="h-5 w-5" />
          </button>
          <button className="flex h-9 w-9 items-center justify-center rounded-full bg-[#C8102E] text-sm font-black text-white" onClick={() => setView("profile")}>
            SV
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-64 shrink-0 border-r border-[#E5E7EB] bg-white p-4 lg:block">
          <p className="mb-3 px-3 text-xs font-black uppercase text-[#6B7280]">Học tập</p>
          <nav className="space-y-1">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => setView(item.id)}
                className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm font-bold transition ${
                  view === item.id ? "bg-[#FDE7EA] text-[#C8102E]" : "text-[#6B7280] hover:bg-[#F7F7F8] hover:text-[#111827]"
                }`}
              >
                <item.icon className="h-5 w-5" />
                {item.label}
              </button>
            ))}
            <button
              onClick={() => setRecentOpen(true)}
              className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm font-bold text-[#6B7280] transition hover:bg-[#F7F7F8] hover:text-[#111827]"
            >
              <Clock3 className="h-5 w-5" />
              Gần đây
            </button>
          </nav>

          <div className="mt-8 rounded-lg bg-[#FFF4D9] p-4">
            <ShieldCheck className="mb-3 h-5 w-5 text-[#C8102E]" />
            <p className="text-sm font-black">Gợi ý hôm nay</p>
            <p className="mt-1 text-xs leading-5 text-[#6B7280]">Làm lại 10 câu sai trong chủ đề Kỹ thuật truyền thông.</p>
          </div>
        </aside>

        <main className="min-w-0 flex-1 overflow-y-auto p-5 md:p-8 lg:p-12">
          {view === "dashboard" && renderDashboard()}
          {view === "explore" && renderExplore()}
          {view === "settings" && renderSettings()}
          {view === "profile" && renderProfile()}
          {view === "saved" && renderSaved()}
        </main>
      </div>

      {recentOpen && (
        <Modal title="Chủ đề mở gần đây" onClose={() => setRecentOpen(false)} className="max-w-2xl">
          <div className="grid max-h-[65vh] gap-3 overflow-y-auto bg-[#F9FAFB] p-5 sm:grid-cols-2">
            {topics.slice(0, 4).map((topic) => {
              const Icon = topic.icon;
              return (
                <Link key={topic.id} to={`/workspace/${topic.id}`} onClick={() => setRecentOpen(false)}>
                  <Card className="flex h-full gap-3 p-4 transition hover:border-[#C8102E]/45">
                    <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-md ${topic.color}`}>
                      <Icon className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                      <h3 className="truncate font-black">{topic.name}</h3>
                      <p className="mt-1 text-xs text-[#6B7280]">Đã mở {topic.updated}</p>
                    </div>
                  </Card>
                </Link>
              );
            })}
          </div>
        </Modal>
      )}

      {savedTopic && (
        <Modal title="Chọn quiz để học" onClose={() => setSavedTopic(null)} className="max-w-xl">
          <div className="space-y-3 bg-[#F9FAFB] p-5">
            <div className="rounded-lg bg-white p-4">
              <Badge className="mb-2 bg-[#FDE7EA] text-[#C8102E]">{savedTopic.subject}</Badge>
              <h3 className="text-lg font-black">{savedTopic.title}</h3>
              <p className="mt-1 text-sm text-[#6B7280]">Tác giả: {savedTopic.author}</p>
            </div>
            {[1, 2, 3].map((item) => (
              <Card key={item} className="flex items-center justify-between gap-3 p-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-[#FDE7EA] text-[#C8102E]">
                    <FileQuestion className="h-5 w-5" />
                  </div>
                  <div>
                    <h4 className="font-black">Quiz ôn tập phần {item}</h4>
                    <p className="text-xs text-[#6B7280]">{item * 10 + 5} câu - {item * 15} phút</p>
                  </div>
                </div>
                <Link to={`/quiz/${savedTopic.id * 10 + item}/take`}>
                  <Button size="sm">Bắt đầu</Button>
                </Link>
              </Card>
            ))}
          </div>
        </Modal>
      )}

      {deleteTopic && (
        <Modal title="Xóa chủ đề?" onClose={() => setDeleteTopic(null)} className="max-w-sm">
          <div className="p-5">
            <p className="text-sm leading-6 text-[#6B7280]">
              Bạn đang chọn xóa <b>{deleteTopic.name}</b>. Trong bản demo, thao tác này chỉ hiển thị thông báo.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setDeleteTopic(null)}>Hủy</Button>
              <Button
                variant="danger"
                onClick={() => {
                  toast.error("Đã mô phỏng xóa chủ đề.");
                  setDeleteTopic(null);
                }}
              >
                <Trash2 className="h-4 w-4" />
                Xóa
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
