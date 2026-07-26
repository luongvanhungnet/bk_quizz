import { LogIn, ShieldAlert } from "lucide-react";
import { Link } from "react-router";
import { Button, Card } from "../app/components/ui";

export function AccessDenied({
  returnTo,
  authenticated = false,
  onUseAnotherAccount,
}: {
  returnTo: string;
  authenticated?: boolean;
  onUseAnotherAccount?: () => void;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#FFF4D9] px-5 py-24">
      <Card className="w-full max-w-lg border-amber-200 p-8 text-center shadow-xl">
        <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-amber-100 text-amber-700">
          <ShieldAlert aria-hidden="true" className="h-7 w-7" />
        </span>
        <h1 className="mt-5 text-2xl font-black">
          Bạn không có quyền truy cập trang này
        </h1>
        <p className="mt-3 text-sm leading-6 text-[#6B7280]">
          Vui lòng đăng nhập bằng tài khoản có quyền phù hợp để tiếp tục.
        </p>
        {authenticated ? (
          <Button className="mt-6" onClick={onUseAnotherAccount}>
            <LogIn className="h-4 w-4" />
            Đăng nhập bằng tài khoản khác
          </Button>
        ) : (
          <Link state={{ from: returnTo }} to="/login">
            <Button className="mt-6">
              <LogIn className="h-4 w-4" />
              Đăng nhập để tiếp tục
            </Button>
          </Link>
        )}
      </Card>
    </main>
  );
}
