import { useEffect, useState } from "react";
import { Button } from "./ui";

export function EmailVerificationAction({
  email,
  onResend,
}: {
  email: string;
  onResend: (email: string) => Promise<void>;
}) {
  const [sending, setSending] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (cooldown < 1) return;
    const timer = window.setTimeout(() => setCooldown((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  async function resend() {
    if (sending || cooldown > 0) return;
    setSending(true);
    setMessage("");
    setFailed(false);
    try {
      await onResend(email);
      setCooldown(30);
      setMessage("Email xác thực đã được xếp hàng gửi.");
    } catch (error) {
      setFailed(true);
      setMessage(error instanceof Error ? error.message : "Không thể gửi email xác thực. Vui lòng thử lại.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 p-4">
      <p className="text-sm font-bold text-amber-900">Email của bạn chưa được xác minh.</p>
      <p className="mt-1 text-sm text-amber-800">Xác minh email để có thể xuất bản, dùng AI và tạo lớp học.</p>
      <Button className="mt-3" size="sm" disabled={sending || cooldown > 0} onClick={() => void resend()}>
        {sending ? "Đang gửi..." : cooldown > 0 ? `Gửi lại sau ${cooldown}s` : "Gửi email xác thực"}
      </Button>
      {message && <p className={`mt-2 text-sm ${failed ? "text-red-700" : "text-green-700"}`}>{message}</p>}
    </div>
  );
}
