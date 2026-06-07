import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router";
import { ArrowLeft, CheckCircle2, Mail, Zap } from "lucide-react";
import { toast } from "sonner";
import { Button, Card, Input } from "../components/ui";

export default function ForgotPassword() {
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setTimeout(() => {
      setSubmitted(true);
      setLoading(false);
      toast.success("Đã gửi link đặt lại mật khẩu demo.");
    }, 600);
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
          <p className="mb-4 text-sm font-black uppercase text-[#C8102E]">Forgot Password</p>
          <h1 className="text-4xl font-black leading-tight">Quên mật khẩu thì lấy lại trong vài phút.</h1>
          <p className="mt-4 text-sm leading-6 text-white/60">
            Nhập email đã đăng ký. BKQuiz sẽ gửi link đặt lại nếu email tồn tại trong hệ thống.
          </p>
        </div>
        <div className="grid grid-cols-6 gap-3 opacity-80">
          {Array.from({ length: 36 }).map((_, index) => (
            <span key={index} className={`h-1.5 w-1.5 rounded-full ${index % 6 === 0 ? "bg-[#C8102E]" : "bg-white/15"}`} />
          ))}
        </div>
      </aside>

      <main className="flex min-h-screen items-center justify-center px-5 py-10">
        <div className="w-full max-w-[350px] sm:max-w-md">
          <Link to="/login" className="mb-6 inline-flex items-center gap-2 text-sm font-bold text-[#6B7280] hover:text-[#111827]">
            <ArrowLeft className="h-4 w-4" />
            Quay lại đăng nhập
          </Link>

          <Card className="p-6 shadow-xl md:p-8">
            {!submitted ? (
              <>
                <h2 className="text-2xl font-black">Quên mật khẩu?</h2>
                <p className="mt-2 text-sm leading-6 text-[#6B7280]">
                  Nhập email của bạn và chúng tôi sẽ gửi liên kết để đặt lại mật khẩu.
                </p>
                <form className="mt-7 space-y-5" onSubmit={submit}>
                  <div>
                    <label className="mb-1.5 block text-sm font-bold">Email</label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9CA3AF]" />
                      <Input className="pl-9" type="email" required placeholder="mssv@hust.edu.vn" />
                    </div>
                  </div>
                  <Button type="submit" className="w-full" size="lg" disabled={loading}>
                    {loading ? "Đang gửi..." : "Gửi link đặt lại"}
                  </Button>
                  <p className="text-center text-xs leading-5 text-[#6B7280]">
                    Nếu email tồn tại, bạn sẽ nhận được link trong vài phút.
                  </p>
                </form>
              </>
            ) : (
              <div className="py-4 text-center">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[#F0FDF4]">
                  <CheckCircle2 className="h-7 w-7 text-[#16A34A]" />
                </div>
                <h2 className="text-2xl font-black">Đã gửi email</h2>
                <p className="mt-3 text-sm leading-6 text-[#6B7280]">
                  Vui lòng kiểm tra hộp thư đến và thư mục spam. Link demo sẽ hết hạn sau 15 phút.
                </p>
                <Link to="/login">
                  <Button className="mt-7 w-full" variant="outline">
                    Quay lại đăng nhập
                  </Button>
                </Link>
              </div>
            )}
          </Card>
        </div>
      </main>
    </div>
  );
}
