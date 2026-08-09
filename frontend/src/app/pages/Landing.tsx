import { Link } from "react-router";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock3,
  HelpCircle,
  MessageSquareText,
  Settings2,
  Sparkles,
  UploadCloud,
} from "lucide-react";
import { Button, Card } from "../components/ui";
import { plans } from "../content/pricing";

const features = [
  {
    icon: UploadCloud,
    title: "Upload tài liệu",
    desc: "PDF, PPT, DOCX, ảnh hoặc ghi chú môn học đều có thể trở thành nguồn tạo câu hỏi.",
  },
  {
    icon: Settings2,
    title: "Cấu hình dạng câu",
    desc: "Chọn số câu trắc nghiệm, nhiều đáp án, điền khuyết, tự luận và thời lượng làm bài.",
  },
  {
    icon: Sparkles,
    title: "Sinh đề & biên tập",
    desc: "AI tạo bản nháp, bạn xem lại, sửa câu hỏi, thêm giải thích và xuất file khi cần.",
  },
  {
    icon: Clock3,
    title: "Thi thử có timer",
    desc: "Mô phỏng trải nghiệm làm bài nghiêm túc: đếm ngược, autosave, đánh dấu câu.",
  },
  {
    icon: CheckCircle2,
    title: "Chấm điểm tức thì",
    desc: "Nộp bài là thấy điểm, câu đúng/sai, giải thích và gợi ý ôn lại phần yếu.",
  },
  {
    icon: MessageSquareText,
    title: "Hỏi AI theo tài liệu",
    desc: "Không hiểu câu nào thì mở mini chat để hỏi ngay trong ngữ cảnh chủ đề.",
  },
];

const faq = [
  "BKQuiz có miễn phí không?",
  "Có thể upload tối đa bao nhiêu file?",
  "AI có bám sát nội dung slide không?",
  "Có xuất được PDF, Word hoặc CSV không?",
  "Giảng viên có thể dùng để tạo ngân hàng câu hỏi không?",
  "Dữ liệu học tập có được lưu lại không?",
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-[#FFF4D9] font-sans text-[#111827]">
      <header className="sticky top-0 z-40 border-b border-black/5 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-end gap-8 px-5 md:justify-between lg:px-8">
          <nav className="hidden items-center gap-7 text-sm font-semibold text-[#6B7280] md:flex">
            <a href="#features" className="hover:text-[#111827]">Tính năng</a>
            <a href="#compare" className="hover:text-[#111827]">So sánh</a>
            <Link to="/pricing" className="hover:text-[#111827]">Bảng giá</Link>
            <a href="#faq" className="hover:text-[#111827]">FAQ</a>
          </nav>
          <div className="flex items-center gap-3">
            <Link to="/login" className="hidden text-sm font-semibold text-[#6B7280] hover:text-[#C8102E] sm:block">
              Đăng nhập
            </Link>
            <Link to="/register">
              <Button size="sm">Dùng thử miễn phí</Button>
            </Link>
          </div>
        </div>
      </header>

      <main>
        <section className="mx-auto grid max-w-7xl gap-10 px-5 py-12 lg:grid-cols-[1fr_520px] lg:px-8 lg:py-20">
          <div className="flex flex-col justify-center">
            <div className="mb-5 inline-flex w-fit items-center gap-2 rounded-full border border-[#F6C9D0] bg-white px-3 py-1 text-sm font-bold text-[#C8102E]">
              <span className="h-2 w-2 rounded-full bg-[#C8102E]" />
              AI quiz generator cho sinh viên HUST
            </div>
            <h1 className="max-w-3xl text-4xl font-black leading-tight tracking-normal md:text-6xl">
              Ôn GK/CK đúng format Bách Khoa, tạo quiz từ slide trong 1 phút
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-[#4B5563] md:text-lg">
              Upload tài liệu môn học, BKQuiz sinh đề trắc nghiệm, điền đáp án, tự luận và cho làm thử tính giờ như hệ thống thi của trường.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link to="/register">
                <Button size="lg" className="w-full sm:w-auto">
                  Tạo project mới
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link to="/dashboard">
                <Button size="lg" variant="outline" className="w-full sm:w-auto bg-white">
                  Vào ứng dụng
                </Button>
              </Link>
            </div>

            <div className="mt-12 grid max-w-2xl grid-cols-3 gap-3">
              {[
                ["AI", "sinh quiz từ tài liệu"],
                ["3", "dạng câu hỏi hỗ trợ"],
                ["24/7", "tự động lưu tiến độ"],
              ].map(([value, label]) => (
                <Card key={label} className="bg-white/80 p-4">
                  <div className="text-2xl font-black text-[#C8102E]">{value}</div>
                  <div className="mt-1 text-xs font-semibold text-[#6B7280]">{label}</div>
                </Card>
              ))}
            </div>
          </div>

          <div className="relative min-h-[430px] overflow-hidden rounded-lg border border-black/10 bg-white p-4 shadow-2xl">
            <div className="absolute left-0 top-0 h-full w-24 bg-[#111111] p-4 text-white">
              <div className="mb-8 text-sm font-black">Menu</div>
              {["Nguồn", "Quiz", "Thi thử", "Kết quả"].map((item, index) => (
                <div
                  key={item}
                  className={`mb-2 rounded px-2 py-2 text-xs font-semibold ${index === 1 ? "bg-[#C8102E]" : "bg-white/10 text-white/65"}`}
                >
                  {item}
                </div>
              ))}
            </div>
            <div className="ml-28">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-xs font-bold uppercase text-[#C8102E]">Workspace preview</p>
                  <h2 className="mt-1 text-xl font-black">Tạo quiz</h2>
                </div>
                <Button size="sm">Generate</Button>
              </div>
              <div className="grid gap-3 rounded-lg bg-[#FFF8E8] p-4">
                <div className="grid grid-cols-3 gap-2">
                  {["Dễ", "Trung bình", "Khó"].map((level) => (
                    <div key={level} className={`rounded border px-3 py-2 text-center text-xs font-bold ${level === "Trung bình" ? "border-[#C8102E] bg-white text-[#C8102E]" : "border-[#E5E7EB] bg-white text-[#6B7280]"}`}>
                      {level}
                    </div>
                  ))}
                </div>
                {["Trắc nghiệm 1 đáp án", "Trắc nghiệm nhiều đáp án", "Điền vào chỗ trống", "Tự luận ngắn"].map((type, index) => (
                  <div key={type} className="flex items-center justify-between rounded border border-[#E5E7EB] bg-white p-3">
                    <span className="text-sm font-semibold">{type}</span>
                    <span className="rounded bg-[#FDE7EA] px-2 py-1 text-xs font-black text-[#C8102E]">{[20, 5, 3, 2][index]}</span>
                  </div>
                ))}
              </div>
              <div className="mt-4 grid gap-2 rounded-lg border border-[#E5E7EB] bg-[#F7F7F8] p-3">
                {[
                  ["Q1", "TCP thuộc tầng nào trong mô hình OSI?", "Trắc nghiệm"],
                  ["Q2", "Chọn các giao thức tầng giao vận", "Nhiều đáp án"],
                  ["Q3", "Điền khuyết về PCM", "Điền khuyết"],
                ].map(([id, text, type]) => (
                  <div key={id} className="flex items-center gap-3 rounded-md bg-white p-3">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-[#FDE7EA] text-xs font-black text-[#C8102E]">
                      {id}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-bold">{text}</p>
                      <p className="text-xs text-[#6B7280]">{type}</p>
                    </div>
                    <CheckCircle2 className="h-4 w-4 text-[#16A34A]" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="features" className="bg-white py-16">
          <div className="mx-auto max-w-7xl px-5 lg:px-8">
            <div className="mb-10 flex flex-col justify-between gap-4 md:flex-row md:items-end">
              <div>
                <p className="text-sm font-black uppercase text-[#C8102E]">Tính năng</p>
                <h2 className="mt-2 text-3xl font-black">BKQuiz làm được gì?</h2>
              </div>
              <p className="max-w-xl text-sm leading-6 text-[#6B7280]">
                Tập trung vào thao tác học thật: tạo đề nhanh, sửa nhanh, thi thử nghiêm túc và xem lại lỗi ngay.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {features.map((feature) => (
                <Card key={feature.title} className="p-5 transition hover:-translate-y-0.5 hover:shadow-md">
                  <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-md bg-[#FDE7EA] text-[#C8102E]">
                    <feature.icon className="h-5 w-5" />
                  </div>
                  <h3 className="font-black">{feature.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-[#6B7280]">{feature.desc}</p>
                </Card>
              ))}
            </div>
          </div>
        </section>

        <section id="compare" className="mx-auto max-w-6xl px-5 py-16 lg:px-8">
          <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
            <Card className="overflow-hidden bg-white">
              <div className="border-b border-[#E5E7EB] p-5">
                <h2 className="text-2xl font-black">Khác gì so với công cụ khác?</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="bg-[#F7F7F8] text-xs uppercase text-[#6B7280]">
                    <tr>
                      <th className="px-5 py-4">Tiêu chí</th>
                      <th className="px-5 py-4 text-[#C8102E]">BKQuiz</th>
                      <th className="px-5 py-4">ChatGPT</th>
                      <th className="px-5 py-4">Quizlet/Kahoot</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#E5E7EB]">
                    {[
                      ["Bám sát format BK", true, false, false],
                      ["Thi thử có timer", true, false, true],
                      ["Nhiều dạng câu học thuật", true, true, false],
                      ["Giải thích câu sai", true, true, false],
                    ].map(([label, bk, gpt, quiz]) => (
                      <tr key={String(label)}>
                        <td className="px-5 py-4 font-semibold">{label}</td>
                        {[bk, gpt, quiz].map((ok, index) => (
                          <td key={index} className="px-5 py-4">
                            {ok ? <CheckCircle2 className="h-5 w-5 text-[#16A34A]" /> : <span className="block h-px w-5 bg-[#D1D5DB]" />}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card className="bg-[#111111] p-6 text-white">
              <BookOpen className="mb-5 h-8 w-8 text-[#C8102E]" />
              <h3 className="text-2xl font-black">Thiết kế cho nhịp ôn thi thật.</h3>
              <p className="mt-3 text-sm leading-6 text-white/65">
                Không cố trở thành mạng xã hội học tập. BKQuiz ưu tiên tạo đề, làm bài, xem lại và quay về slide đúng phần cần ôn.
              </p>
              <Link to="/pricing">
                <Button variant="outline" className="mt-6 border-white/20 bg-white text-[#111827] hover:bg-[#FFF4D9]">
                  Xem bảng giá
                </Button>
              </Link>
            </Card>
          </div>
        </section>

        <section className="bg-white py-16">
          <div className="mx-auto max-w-7xl px-5 lg:px-8">
            <div className="mb-8 text-center">
              <p className="text-sm font-black uppercase text-[#C8102E]">Gói sử dụng</p>
              <h2 className="mt-2 text-3xl font-black">Chọn gói phù hợp với bạn</h2>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              {plans.map((plan) => (
                <Card key={plan.name} className={`p-6 ${plan.highlighted ? "border-[#C8102E] shadow-lg" : ""}`}>
                  <h3 className="text-xl font-black">{plan.name}</h3>
                  <p className="mt-1 text-sm text-[#6B7280]">{plan.description}</p>
                  <div className="mt-5 text-3xl font-black text-[#C8102E]">{plan.price}</div>
                  <ul className="mt-5 space-y-2 text-sm text-[#4B5563]">
                    {plan.features.slice(0, 3).map((feature) => (
                      <li key={feature} className="flex gap-2">
                        <CheckCircle2 className="mt-0.5 h-4 w-4 text-[#16A34A]" />
                        {feature}
                      </li>
                    ))}
                  </ul>
                </Card>
              ))}
            </div>
          </div>
        </section>

        <section id="faq" className="mx-auto max-w-4xl px-5 py-16 lg:px-8">
          <div className="mb-8 text-center">
            <HelpCircle className="mx-auto mb-3 h-8 w-8 text-[#C8102E]" />
            <h2 className="text-3xl font-black">FAQ</h2>
          </div>
          <div className="grid gap-3">
            {faq.map((item) => (
              <Card key={item} className="flex items-center justify-between bg-white p-4">
                <span className="font-semibold">{item}</span>
                <ArrowRight className="h-4 w-4 text-[#9CA3AF]" />
              </Card>
            ))}
          </div>
        </section>
      </main>

      <footer className="border-t border-black/5 bg-white px-5 py-8">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 text-sm text-[#6B7280] md:flex-row md:items-center md:justify-between">
          <p>© 2026 BKQuiz. Nền tảng ôn tập dành cho sinh viên Bách Khoa.</p>
          <div className="flex gap-5">
            <a href="#" className="hover:text-[#111827]">Liên hệ</a>
            <a href="#" className="hover:text-[#111827]">Điều khoản</a>
            <a href="#" className="hover:text-[#111827]">Privacy</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
