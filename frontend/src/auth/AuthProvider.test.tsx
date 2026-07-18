import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { createAuthApi } from "./api";
import { accessTokenStore } from "./accessToken";
import { AuthProvider, useAuth } from "./AuthProvider";

const user = {
  id: "user-1",
  username: "Nguyễn Văn A",
  email: "student@example.com",
  role: "STUDENT" as const,
  emailVerified: true,
  active: true,
};

function AuthState() {
  const { status, user: currentUser } = useAuth();
  return <div>{`${status}:${currentUser?.username ?? "none"}`}</div>;
}

function LoginControl() {
  const { login, status, user: currentUser } = useAuth();
  return (
    <button type="button" onClick={() => void login({ email: "student@example.com", password: "secret123" })}>
      {`${status}:${currentUser?.username ?? "Đăng nhập"}`}
    </button>
  );
}

function RegisterControl() {
  const { register, status, user: currentUser } = useAuth();
  return (
    <button
      type="button"
      onClick={() =>
        void register({ username: "Nguyễn Văn A", email: "student@example.com", password: "secret123" })
      }
    >
      {`${status}:${currentUser?.username ?? "Đăng ký"}`}
    </button>
  );
}

function LogoutControl() {
  const { logout, status } = useAuth();
  return (
    <button type="button" onClick={() => void logout()}>
      {status}
    </button>
  );
}

describe("AuthProvider", () => {
  it("restores the cookie-backed session and keeps the access token in memory", async () => {
    accessTokenStore.clear();
    const service = {
      refresh: vi.fn().mockResolvedValue({ accessToken: "restored-token", expiresIn: 300, user }),
    } as unknown as ReturnType<typeof createAuthApi>;

    render(
      <AuthProvider service={service}>
        <AuthState />
      </AuthProvider>,
    );

    expect(screen.getByText("loading:none")).toBeInTheDocument();
    expect(await screen.findByText("authenticated:Nguyễn Văn A")).toBeInTheDocument();
    expect(accessTokenStore.get()).toBe("restored-token");
  });

  it("commits the authenticated user after login", async () => {
    const service = {
      refresh: vi.fn().mockRejectedValue(new Error("No session")),
      login: vi.fn().mockResolvedValue({ accessToken: "login-token", expiresIn: 300, user }),
    } as unknown as ReturnType<typeof createAuthApi>;

    render(
      <AuthProvider service={service}>
        <LoginControl />
      </AuthProvider>,
    );
    const control = await screen.findByRole("button", { name: "anonymous:Đăng nhập" });
    await userEvent.click(control);

    expect(await screen.findByRole("button", { name: "authenticated:Nguyễn Văn A" })).toBeInTheDocument();
    expect(accessTokenStore.get()).toBe("login-token");
  });

  it("commits the authenticated user after registration", async () => {
    const service = {
      refresh: vi.fn().mockRejectedValue(new Error("No session")),
      register: vi.fn().mockResolvedValue({ accessToken: "register-token", expiresIn: 300, user }),
    } as unknown as ReturnType<typeof createAuthApi>;

    render(
      <AuthProvider service={service}>
        <RegisterControl />
      </AuthProvider>,
    );
    const control = await screen.findByRole("button", { name: "anonymous:Đăng ký" });
    await userEvent.click(control);

    expect(await screen.findByRole("button", { name: "authenticated:Nguyễn Văn A" })).toBeInTheDocument();
    expect(service.register).toHaveBeenCalledWith({
      username: "Nguyễn Văn A",
      email: "student@example.com",
      password: "secret123",
    });
    expect(accessTokenStore.get()).toBe("register-token");
  });

  it("clears the in-memory session after logout", async () => {
    const service = {
      refresh: vi.fn().mockResolvedValue({ accessToken: "restored-token", expiresIn: 300, user }),
      logout: vi.fn().mockResolvedValue(null),
    } as unknown as ReturnType<typeof createAuthApi>;

    render(
      <AuthProvider service={service}>
        <LogoutControl />
      </AuthProvider>,
    );
    const control = await screen.findByRole("button", { name: "authenticated" });
    await userEvent.click(control);

    expect(await screen.findByRole("button", { name: "anonymous" })).toBeInTheDocument();
    expect(accessTokenStore.get()).toBeNull();
  });

  it("becomes anonymous when automatic refresh clears an expired token", async () => {
    const service = {
      refresh: vi.fn().mockResolvedValue({ accessToken: "restored-token", expiresIn: 300, user }),
    } as unknown as ReturnType<typeof createAuthApi>;

    render(
      <AuthProvider service={service}>
        <AuthState />
      </AuthProvider>,
    );
    expect(await screen.findByText("authenticated:Nguyễn Văn A")).toBeInTheDocument();

    act(() => accessTokenStore.clear());

    expect(await screen.findByText("anonymous:none")).toBeInTheDocument();
  });
});
