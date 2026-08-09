import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { GraduationCap, Mail, UserRound } from "lucide-react";
import { toast } from "sonner";
import { ApiRequestError } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { Button, Card, Checkbox, Input } from "../components/ui";

export default function Register() {
  const navigate = useNavigate();
  const { register } = useAuth();
  const [loading, setLoading] = useState(false);
  const [accepted, setAccepted] = useState(true);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [accountType, setAccountType] = useState<"STUDENT" | "TEACHER">("STUDENT");
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (!accepted) {
      toast.error("Bạn cần đồng ý điều khoản để tạo tài khoản.");
      return;
    }
    if (username.trim().length < 3 || !email.includes("@")) {
      setError("Vui lòng nhập đầy đủ họ tên và email hợp lệ.");
      return;
    }
    if (password.length < 8 || password.length > 128) {
      setError("Mật khẩu tối thiểu 8 ký tự và tối đa 128 ký tự.");
      return;
    }
    if (!/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/.test(password)) {
      setError("Mật khẩu phải có chữ thường, chữ hoa và chữ số.");
      return;
    }
    if (password !== confirmation) {
      setError("Mật khẩu xác nhận không khớp.");
      return;
    }

    setLoading(true);
    try {
      const registeredUser = await register({ username: username.trim(), email: email.trim(), password, accountType });
      toast.success("Tạo tài khoản thành công. Vui lòng kiểm tra email để xác minh tài khoản.");
      navigate(registeredUser.role === "TEACHER" ? "/classrooms" : "/dashboard", { replace: true });
    } catch (cause) {
      const message = cause instanceof ApiRequestError ? cause.message : "Không thể tạo tài khoản. Vui lòng thử lại.";
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100dvh-4rem)] bg-[#FFF4D9] font-sans text-[#111827] lg:grid lg:grid-cols-[420px_1fr]">
      <aside className="bk-auth-grid hidden min-h-[calc(100dvh-4rem)] flex-col justify-between p-8 text-white lg:flex">
        <div className="max-w-xs">
          <p className="mb-4 text-sm font-black uppercase text-[#C8102E]">Auth Register</p>
          <h1 className="text-4xl font-black leading-tight">Tạo tài khoản để biến tài liệu thành quiz.</h1>
          <p className="mt-4 text-sm leading-6 text-white/60">
            Đăng ký tài khoản sinh viên, sau đó vào dashboard để bắt đầu tạo chủ đề học tập.
          </p>
        </div>
        <div className="grid grid-cols-6 gap-3 opacity-80">
          {Array.from({ length: 36 }).map((_, index) => (
            <span key={index} className={`h-1.5 w-1.5 rounded-full ${index % 4 === 0 ? "bg-[#C8102E]" : "bg-white/15"}`} />
          ))}
        </div>
      </aside>

      <main className="flex min-h-[calc(100dvh-4rem)] items-center justify-center px-5 py-10">
        <div className="w-full max-w-[350px] sm:max-w-md">
          <div className="mb-8 flex items-center justify-end lg:hidden">
            <Link to="/login" className="text-sm font-bold text-[#C8102E]">Đăng nhập</Link>
          </div>

          <Card className="p-6 shadow-xl md:p-8">
            <h2 className="text-2xl font-black">Tạo tài khoản BKQuiz</h2>
            <p className="mt-2 text-sm text-[#6B7280]">Bắt đầu tạo quiz từ tài liệu học tập của bạn.</p>

            <form className="mt-7 space-y-5" onSubmit={submit}>
              <fieldset>
                <legend className="mb-2 text-sm font-bold">Loại tài khoản</legend>
                <div className="grid grid-cols-2 gap-2">
                  {(["STUDENT", "TEACHER"] as const).map((role) => (
                    <button key={role} type="button" onClick={() => setAccountType(role)}
                      className={`rounded-lg border px-4 py-3 text-left text-sm ${accountType === role ? "border-[#C8102E] bg-[#FDE7EA] text-[#C8102E]" : "bg-white"}`}>
                      <b>{role === "STUDENT" ? "Sinh viên" : "Giáo viên"}</b>
                    </button>
                  ))}
                </div>
                {accountType === "TEACHER" && <p className="mt-2 text-xs text-[#6B7280]">Bạn cần xác minh email trước khi tạo lớp hoặc chia sẻ nội dung.</p>}
              </fieldset>

              <div>
                <label htmlFor="register-username" className="mb-1.5 block text-sm font-bold">Họ và tên</label>
                <div className="relative">
                  <UserRound className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9CA3AF]" />
                  <Input id="register-username" className="pl-9" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="name" required placeholder="Nguyễn Văn A" />
                </div>
              </div>

              <div>
                <label htmlFor="register-email" className="mb-1.5 block text-sm font-bold">Email</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9CA3AF]" />
                  <Input id="register-email" className="pl-9" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required placeholder="mssv@hust.edu.vn" />
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="register-password" className="mb-1.5 block text-sm font-bold">Mật khẩu</label>
                  <Input id="register-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required minLength={8} maxLength={128} placeholder="Tối thiểu 8 ký tự" />
                </div>
                <div>
                  <label htmlFor="register-confirmation" className="mb-1.5 block text-sm font-bold">Xác nhận</label>
                  <Input id="register-confirmation" type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" required placeholder="Nhập lại" />
                </div>
              </div>

              {error && <p className="text-xs font-semibold text-[#DC2626]">{error}</p>}

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
