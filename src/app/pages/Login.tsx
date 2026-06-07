import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { Eye, EyeOff, LockKeyhole, Mail, Zap } from "lucide-react";
import { toast } from "sonner";
import { Button, Card, Checkbox, Input } from "../components/ui";

export default function Login() {
  const navigate = useNavigate();
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState("sinhvien@hust.edu.vn");
  const [password, setPassword] = useState("bkquiz-demo");
  const [error, setError] = useState("");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError("");

    if (!email.includes("@") || password.length < 6) {
      setError("Vui lòng nhập email hợp lệ và mật khẩu tối thiểu 6 ký tự.");
      toast.error("Thông tin đăng nhập chưa hợp lệ");
      return;
    }

    setLoading(true);
    setTimeout(() => {
      toast.success("Đăng nhập thành công. Chào mừng quay lại BKQuiz!");
      navigate("/dashboard");
    }, 650);
  };

  return (
    <div className="min-h-screen bg-[#FFF4D9] font-sans text-[#111827] lg:grid lg:grid-cols-[420px_1fr]">
      <aside className="bk-auth-grid relative hidden min-h-screen overflow-hidden p-8 text-white lg:flex lg:flex-col lg:justify-between">
        <Link to="/" className="flex items-center gap-2 text-xl font-black">
          <span className="flex h-9 w-9 items-center justify-center rounded bg-[#C8102E]">
            <Zap className="h-5 w-5 fill-current" />
          </span>
          BKQuiz
        </Link>
        <div className="max-w-xs">
          <p className="mb-4 text-sm font-black uppercase text-[#C8102E]">Auth Login</p>
          <h1 className="text-4xl font-black leading-tight">Từ slide thành đề ôn tập chỉ trong vài phút.</h1>
          <p className="mt-4 text-sm leading-6 text-white/60">
            Đăng nhập để tiếp tục tạo quiz, luyện đề có timer và xem lại phần kiến thức cần ôn.
          </p>
        </div>
        <div className="grid grid-cols-6 gap-3 opacity-80">
          {Array.from({ length: 36 }).map((_, index) => (
            <span key={index} className={`h-1.5 w-1.5 rounded-full ${index % 5 === 0 ? "bg-[#C8102E]" : "bg-white/15"}`} />
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
            <Link to="/register" className="text-sm font-bold text-[#C8102E]">Đăng ký</Link>
          </div>

          <Card className="p-6 shadow-xl md:p-8">
            <h2 className="text-2xl font-black">Đăng nhập BKQuiz</h2>
            <p className="mt-2 text-sm text-[#6B7280]">Tiếp tục không gian học tập của bạn.</p>

            <form className="mt-7 space-y-5" onSubmit={submit}>
              <div>
                <label className="mb-1.5 block text-sm font-bold">Email sinh viên / cá nhân</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9CA3AF]" />
                  <Input
                    className="pl-9"
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="mssv@hust.edu.vn"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-bold">Mật khẩu</label>
                <div className="relative">
                  <LockKeyhole className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9CA3AF]" />
                  <Input
                    className="pl-9 pr-10"
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Nhập mật khẩu"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 rounded p-1 text-[#6B7280] hover:bg-[#F7F7F8]"
                    aria-label="Hiện/ẩn mật khẩu"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                {error && <p className="mt-2 text-xs font-semibold text-[#DC2626]">{error}</p>}
              </div>

              <div className="flex items-center justify-between gap-4">
                <label className="flex cursor-pointer items-center gap-2 text-sm text-[#6B7280]">
                  <Checkbox defaultChecked />
                  Ghi nhớ đăng nhập
                </label>
                <Link to="/forgot-password" className="text-sm font-bold text-[#C8102E] hover:underline">
                  Quên mật khẩu?
                </Link>
              </div>

              <Button type="submit" className="w-full" size="lg" disabled={loading}>
                {loading ? "Đang đăng nhập..." : "Đăng nhập"}
              </Button>
            </form>

            <div className="my-6 flex items-center gap-3 text-xs font-semibold text-[#9CA3AF]">
              <span className="h-px flex-1 bg-[#E5E7EB]" />
              hoặc
              <span className="h-px flex-1 bg-[#E5E7EB]" />
            </div>

            <Button
              variant="outline"
              className="w-full"
              onClick={() => toast.info("SSO Google đang ở chế độ demo.")}
            >
              Đăng nhập bằng Google
            </Button>

            <p className="mt-7 text-center text-sm text-[#6B7280]">
              Chưa có tài khoản?{" "}
              <Link to="/register" className="font-black text-[#C8102E] hover:underline">
                Đăng ký
              </Link>
            </p>
          </Card>
        </div>
      </main>
    </div>
  );
}
