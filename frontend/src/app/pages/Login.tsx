import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { Eye, EyeOff, LockKeyhole, Mail } from "lucide-react";
import { toast } from "sonner";
import { ApiRequestError } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { Button, Card, Input } from "../components/ui";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");

    if (!email.includes("@") || password.length < 8) {
      setError("Vui lòng nhập email hợp lệ và mật khẩu tối thiểu 8 ký tự.");
      toast.error("Thông tin đăng nhập chưa hợp lệ");
      return;
    }

    setLoading(true);
    try {
      const authenticatedUser = await login({ email: email.trim(), password });
      toast.success("Đăng nhập thành công. Chào mừng quay lại BKQuiz!");
      const from = (location.state as { from?: unknown } | null)?.from;
      navigate(typeof from === "string" ? from : authenticatedUser?.role === "ADMIN" ? "/admin" : authenticatedUser?.role === "TEACHER" ? "/classrooms" : "/dashboard", { replace: true });
    } catch (cause) {
      const message = cause instanceof ApiRequestError ? cause.message : "Không thể đăng nhập. Vui lòng thử lại.";
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100dvh-4rem)] bg-[#FFF4D9] font-sans text-[#111827] lg:grid lg:grid-cols-[420px_1fr]">
      <aside className="bk-auth-grid relative hidden min-h-[calc(100dvh-4rem)] overflow-hidden p-8 text-white lg:flex lg:flex-col lg:justify-between">
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

      <main className="flex min-h-[calc(100dvh-4rem)] items-center justify-center px-5 py-10">
        <div className="w-full max-w-[350px] sm:max-w-md">
          <div className="mb-8 flex items-center justify-end lg:hidden">
            <Link to="/register" className="text-sm font-bold text-[#C8102E]">Đăng ký</Link>
          </div>

          <Card className="p-6 shadow-xl md:p-8">
            <h2 className="text-2xl font-black">Đăng nhập BKQuiz</h2>
            <p className="mt-2 text-sm text-[#6B7280]">Tiếp tục không gian học tập của bạn.</p>

            <form className="mt-7 space-y-5" onSubmit={submit}>
              <div>
                <label htmlFor="login-email" className="mb-1.5 block text-sm font-bold">Email sinh viên / cá nhân</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9CA3AF]" />
                  <Input
                    className="pl-9"
                    id="login-email"
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="mssv@hust.edu.vn"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="login-password" className="mb-1.5 block text-sm font-bold">Mật khẩu</label>
                <div className="relative">
                  <LockKeyhole className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9CA3AF]" />
                  <Input
                    className="pl-9 pr-10"
                    id="login-password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
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

              <div className="flex items-center justify-end">
                <Link to="/forgot-password" className="text-sm font-bold text-[#C8102E] hover:underline">
                  Quên mật khẩu?
                </Link>
              </div>

              <Button type="submit" className="w-full" size="lg" disabled={loading}>
                {loading ? "Đang đăng nhập..." : "Đăng nhập"}
              </Button>
            </form>

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
