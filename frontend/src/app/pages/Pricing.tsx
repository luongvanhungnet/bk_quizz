import { Link } from "react-router";
import { CheckCircle2, HelpCircle, Zap } from "lucide-react";
import { Button, Card } from "../components/ui";
import { plans } from "../content/pricing";

export default function Pricing() {
  return (
    <div className="min-h-screen bg-[#F7F7F8] font-sans text-[#111827]">
      <header className="border-b border-[#E5E7EB] bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 lg:px-8">
          <Link to="/" className="flex items-center gap-2 text-xl font-black text-[#C8102E]">
            <Zap className="h-6 w-6 fill-current" />
            BKQuiz
          </Link>
          <nav className="hidden items-center gap-6 text-sm font-semibold text-[#6B7280] md:flex">
            <Link to="/">Trang chủ</Link>
            <Link to="/dashboard">Ứng dụng</Link>
            <Link to="/login">Đăng nhập</Link>
          </nav>
          <Link to="/register">
            <Button size="sm">Dùng thử miễn phí</Button>
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 py-14 lg:px-8">
        <div className="text-center">
          <p className="text-sm font-black uppercase text-[#C8102E]">Pricing</p>
          <h1 className="mt-2 text-4xl font-black">Hãy chọn gói phù hợp với bạn</h1>
          <p className="mx-auto mt-4 max-w-2xl text-[#6B7280]">
            Bắt đầu miễn phí, nâng cấp khi bạn cần tạo nhiều đề hơn hoặc dùng cho lớp học.
          </p>
        </div>

        <div className="mt-10 grid gap-5 md:grid-cols-3">
          {plans.map((plan) => (
            <Card key={plan.name} className={`relative p-6 ${plan.highlighted ? "border-[#C8102E] shadow-xl" : ""}`}>
              {plan.highlighted && (
                <span className="absolute right-5 top-5 rounded bg-[#FDE7EA] px-2 py-1 text-xs font-black text-[#C8102E]">
                  Khuyên dùng
                </span>
              )}
              <h2 className="text-2xl font-black">{plan.name}</h2>
              <p className="mt-2 min-h-10 text-sm leading-6 text-[#6B7280]">{plan.description}</p>
              <div className="mt-6 text-3xl font-black text-[#C8102E]">{plan.price}</div>
              <ul className="mt-6 space-y-3 text-sm text-[#4B5563]">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2">
                    <CheckCircle2 className="mt-0.5 h-4 w-4 text-[#16A34A]" />
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>
              <Button
                className="mt-8 w-full"
                variant={plan.highlighted ? "primary" : "outline"}
                disabled={plan.name !== "Free"}
              >
                {plan.name === "Free" ? "Đăng ký miễn phí" : "Sắp ra mắt"}
              </Button>
            </Card>
          ))}
        </div>

        <Card className="mt-10 grid gap-6 bg-[#FFF4D9] p-6 md:grid-cols-[1fr_auto] md:items-center">
          <div>
            <div className="flex items-center gap-2 text-sm font-black text-[#C8102E]">
              <HelpCircle className="h-4 w-4" />
              Cần dùng cho lớp học?
            </div>
            <h3 className="mt-2 text-2xl font-black">BKQuiz có thể mô phỏng ngân hàng câu hỏi cho nhóm/lớp.</h3>
            <p className="mt-2 text-sm text-[#6B7280]">Thanh toán và nâng cấp gói chưa được triển khai.</p>
          </div>
          <Link to="/dashboard">
            <Button variant="secondary">Vào ứng dụng</Button>
          </Link>
        </Card>
      </main>
    </div>
  );
}
