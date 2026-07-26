import { Navigate, Outlet, useLocation, useNavigate } from "react-router";
import { AccessDenied } from "./AccessDenied";
import { useAuth } from "./AuthProvider";

function LoadingSession() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#FFF4D9] text-sm font-semibold text-[#6B7280]">
      Đang khôi phục phiên đăng nhập...
    </div>
  );
}

export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <LoadingSession />;

  if (status === "anonymous") {
    return (
      <AccessDenied
        returnTo={`${location.pathname}${location.search}${location.hash}`}
      />
    );
  }

  return <Outlet />;
}

export function GuestOnly() {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === "loading") return <LoadingSession />;

  if (status === "authenticated") {
    const from = (location.state as { from?: unknown } | null)?.from;
    return (
      <Navigate
        replace
        to={
          typeof from === "string"
            ? from
            : user?.role === "ADMIN"
              ? "/admin"
              : "/dashboard"
        }
      />
    );
  }

  return <Outlet />;
}

export function RequireAdmin() {
  const { status, user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const returnTo = `${location.pathname}${location.search}${location.hash}`;

  if (status === "loading") return <LoadingSession />;
  if (status === "anonymous") return <AccessDenied returnTo={returnTo} />;

  if (user?.role !== "ADMIN") {
    return (
      <AccessDenied
        authenticated
        returnTo={returnTo}
        onUseAnotherAccount={() => {
          void logout().finally(() => {
            navigate("/login", {
              replace: true,
              state: { from: returnTo },
            });
          });
        }}
      />
    );
  }

  return <Outlet />;
}
