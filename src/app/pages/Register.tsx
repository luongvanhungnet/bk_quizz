import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { GraduationCap, Mail, UserRound, Zap } from "lucide-react";
import { toast } from "sonner";
import { Button, Card, Checkbox, Input } from "../components/ui";

export default function Register() {
  const navigate = useNavigate();
  const [role, setRole] = useState<"student" | "teacher">("student");
  const [loading, setLoading] = useState(false);
  const [accepted, setAccepted] = useState(true);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!accepted) {
      toast.error("Bạn cần đồng ý điều khoản để tạo tài khoản.");
      return;
    }

    setLoading(true);
    setTimeout(() => {
      toast.success("Tài khoản demo đã được tạo.");
      navigate("/dashboard");
    }, 700);
  };

  return (
    <div className="min-h-screen bg-[#FFF4D9] font-sans text-[#111827] lg:grid lg:grid-cols-[420px_1fr]">
      <aside className="bk-auth-grid hidden min-h-screen flex-col justify-between p-8 text-white lg:flex">
        <Link to="/" className="flex items-center gap-2 text-xl font-black">
          <span className="flex h-9 w-9 items-center justify-center rounded bg-[#C8102E]">
            <Zap className="h-5 w-5 fill-current" />
          </span>
          BKQuiz
        </Link>
        <div className="max-w-xs">
          <p className="mb-4 text-sm font-black uppercase text-[#C8102E]">Auth Register</p>
          <h1 className="text-4xl font-black leading-tight">Tạo tài khoản để biến tài liệu thành quiz.</h1>
          <p className="mt-4 text-sm leading-6 text-white/60">
            Chọn vai trò sinh viên hoặc giảng viên, sau đó vào dashboard để thử ngay luồng tạo chủ đề.
          </p>
        </div>
        <div className="grid grid-cols-6 gap-3 opacity-80">
          {Array.from({ length: 36 }).map((_, index) => (
            <span key={index} className={`h-1.5 w-1.5 rounded-full ${index % 4 === 0 ? "bg-[#C8102E]" : "bg-white/15"}`} />
          ))}
        </div>
      </aside>

      <main className="flex min-h-screen items-center justify-center px-5 py-10">
        <div className="w-full max-w-[350px] sm:max-w-md">
          <div className="mb-8 flex items-center justify-between lg:hidden">
            <Link to="/" className="flex items-center gap-2 text-xl font-black text-[#C8102E]">
              <Zap className="h-6 w-6 fill-current" />
              BKQuiz
            </Link>
            <Link to="/login" className="text-sm font-bold text-[#C8102E]">Đăng nhập</Link>
          </div>

          <Card className="p-6 shadow-xl md:p-8">
            <h2 className="text-2xl font-black">Tạo tài khoản BKQuiz</h2>
            <p className="mt-2 text-sm text-[#6B7280]">Bắt đầu với dữ liệu demo, chưa cần backend.</p>

            <form className="mt-7 space-y-5" onSubmit={submit}>
              <div className="rounded-lg border border-[#E5E7EB] bg-[#F7F7F8] p-1">
                {[
                  ["student", "Sinh viên"],
                  ["teacher", "Giảng viên"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setRole(value as "student" | "teacher")}
                    className={`inline-flex h-9 w-1/2 items-center justify-center rounded-md text-sm font-bold transition ${
                      role === value ? "bg-white text-[#C8102E] shadow-sm" : "text-[#6B7280] hover:text-[#111827]"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-bold">Họ và tên</label>
                <div className="relative">
                  <UserRound className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9CA3AF]" />
                  <Input className="pl-9" placeholder="Nguyễn Văn A" />
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-bold">Email</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9CA3AF]" />
                  <Input className="pl-9" type="email" placeholder={role === "student" ? "mssv@hust.edu.vn" : "teacher@hust.edu.vn"} />
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-sm font-bold">Mật khẩu</label>
                  <Input type="password" placeholder="Tối thiểu 6 ký tự" />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-bold">Xác nhận</label>
                  <Input type="password" placeholder="Nhập lại" />
                </div>
              </div>

              <label className="flex cursor-pointer items-start gap-2 text-sm leading-6 text-[#6B7280]">
                <Checkbox checked={accepted} onChange={(event) => setAccepted(event.currentTarget.checked)} className="mt-1" />
                Tôi đồng ý với Điều khoản dịch vụ và Chính sách bảo mật của BKQuiz.
              </label>

              <Button type="submit" className="w-full" size="lg" disabled={loading}>
                <GraduationCap className="h-4 w-4" />
                {loading ? "Đang tạo..." : "Tạo tài khoản"}
              </Button>
            </form>

            <p className="mt-7 text-center text-sm text-[#6B7280]">
              Đã có tài khoản?{" "}
              <Link to="/login" className="font-black text-[#C8102E] hover:underline">
                Đăng nhập
              </Link>
            </p>
          </Card>
        </div>
      </main>
    </div>
  );
}
