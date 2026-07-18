import { Navigate, Outlet, useLocation } from "react-router";
import { useAuth } from "./AuthProvider";

export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#FFF4D9] text-sm font-semibold text-[#6B7280]">
        Đang khôi phục phiên đăng nhập...
      </div>
    );
  }

  if (status === "anonymous") {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}${location.hash}` }}
      />
    );
  }

  return <Outlet />;
}

export function GuestOnly() {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#FFF4D9] text-sm font-semibold text-[#6B7280]">
        Đang khôi phục phiên đăng nhập...
      </div>
    );
  }

  if (status === "authenticated") {
    const from = (location.state as { from?: unknown } | null)?.from;
    return <Navigate to={typeof from === "string" ? from : user?.role === "ADMIN" ? "/admin" : "/dashboard"} replace />;
  }

  return <Outlet />;
}

export function RequireAdmin() {
  const { status, user } = useAuth();
  if (status === "loading") return <div className="flex min-h-screen items-center justify-center">Đang tải...</div>;
  if (status === "anonymous") return <Navigate to="/login" replace />;
  if (user?.role !== "ADMIN") return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}
