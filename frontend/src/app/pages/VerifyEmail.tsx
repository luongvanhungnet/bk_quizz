import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { MailCheck } from "lucide-react";
import { useAuth } from "../../auth/AuthProvider";
import { Button, Card, Input } from "../components/ui";

type State = "verifying" | "success" | "error" | "missing";
const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "Không thể xác minh email. Vui lòng thử lại.";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token")?.trim() ?? "";
  const { user, verifyEmail, resendVerification } = useAuth();
  const [state, setState] = useState<State>(token ? "verifying" : "missing");
  const [error, setError] = useState("");
  const [email, setEmail] = useState(user?.email ?? "");
  const [sending, setSending] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    void verifyEmail(token).then(
      () => setState("success"),
      (reason) => { setError(errorMessage(reason)); setState("error"); },
    );
  }, [token, verifyEmail]);

  useEffect(() => {
    if (cooldown < 1) return;
    const timer = window.setTimeout(() => setCooldown((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  async function resend() {
    if (!email.trim() || sending || cooldown > 0) return;
    setSending(true);
    try {
      await resendVerification(email.trim());
      setCooldown(30);
      setError("Email xác minh mới đã được xếp hàng gửi. Vui lòng kiểm tra hộp thư.");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSending(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#F7F7F8] p-5">
      <Card className="w-full max-w-md p-7 text-center">
        <MailCheck className="mx-auto h-12 w-12 text-[#C8102E]" />
        <h1 className="mt-4 text-2xl font-black">Xác minh email</h1>
        {state === "verifying" && <p className="mt-3">Đang xác minh tài khoản...</p>}
        {state === "success" && (
          <>
            <p className="mt-3 text-green-700">Email đã được xác minh thành công.</p>
            <Link to={user ? "/dashboard" : "/login"}><Button className="mt-5 w-full">Tiếp tục</Button></Link>
          </>
        )}
        {(state === "error" || state === "missing") && (
          <div className="mt-4 space-y-3 text-left">
            <p className="text-sm text-red-700">
              {state === "missing" ? "Liên kết xác minh thiếu token." : error}
            </p>
            <label className="block text-sm font-bold">
              Email tài khoản
              <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </label>
            <Button className="w-full" disabled={sending || cooldown > 0} onClick={() => void resend()}>
              {sending ? "Đang gửi..." : cooldown > 0 ? `Gửi lại sau ${cooldown}s` : "Gửi lại email xác minh"}
            </Button>
            {error && state === "missing" && <p className="text-sm text-[#6B7280]">{error}</p>}
          </div>
        )}
      </Card>
    </main>
  );
}
