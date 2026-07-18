import type { ApiClient } from "../api/client";
import { createAuthApi } from "./api";

describe("createAuthApi", () => {
  it("registers a teacher account explicitly", async () => {
    const request = vi.fn().mockResolvedValue({ accessToken: "token", expiresIn: 300, user: {} });
    const authApi = createAuthApi({ request } as ApiClient);

    await authApi.register({ username: "Giảng viên", email: "teacher@example.com", password: "Strong123", accountType: "TEACHER" });

    expect(request).toHaveBeenCalledWith("/auth/register", expect.objectContaining({
      body: JSON.stringify({ username: "Giảng viên", email: "teacher@example.com", password: "Strong123", accountType: "TEACHER" }),
    }));
  });
  it("verifies an email token and refreshes the authenticated session", async () => {
    const request = vi.fn()
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce({ accessToken: "fresh", expiresIn: 900, user: { emailVerified: true } });
    const authApi = createAuthApi({ request } as ApiClient);

    const payload = await authApi.verifyEmail("verification-token");

    expect(request).toHaveBeenNthCalledWith(1, "/auth/verify-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: "verification-token" }),
    });
    expect(request).toHaveBeenNthCalledWith(2, "/auth/refresh-token", expect.any(Object));
    expect(payload?.user.emailVerified).toBe(true);
  });
  it("registers with username, email and password only", async () => {
    const request = vi.fn().mockResolvedValue({ accessToken: "token", expiresIn: 300, user: {} });
    const authApi = createAuthApi({ request } as ApiClient);

    await authApi.register({ username: "Nguyễn Văn A", email: "student@example.com", password: "secret123" });

    expect(request).toHaveBeenCalledWith("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: "Nguyễn Văn A",
        email: "student@example.com",
        password: "secret123",
      }),
    });
  });

  it("logs in with the backend credential contract", async () => {
    const request = vi.fn().mockResolvedValue({ accessToken: "token", expiresIn: 300, user: {} });
    const authApi = createAuthApi({ request } as ApiClient);

    await authApi.login({ email: "student@example.com", password: "secret123" });

    expect(request).toHaveBeenCalledWith("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "student@example.com", password: "secret123" }),
    });
  });

  it("sends the readable CSRF cookie when refreshing the session", async () => {
    document.cookie = "XSRF-TOKEN=csrf%20token; path=/";
    const request = vi.fn().mockResolvedValue({ accessToken: "token", expiresIn: 300, user: {} });
    const authApi = createAuthApi({ request } as ApiClient);

    await authApi.refresh();

    expect(request).toHaveBeenCalledWith("/auth/refresh-token", {
      method: "POST",
      headers: { "X-XSRF-TOKEN": "csrf token" },
    });
  });

  it("requests a password reset without exposing account existence", async () => {
    const request = vi.fn().mockResolvedValue(null);
    const authApi = createAuthApi({ request } as ApiClient);

    await authApi.forgotPassword("student@example.com");

    expect(request).toHaveBeenCalledWith("/auth/forgot-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "student@example.com" }),
    });
  });

  it("protects logout with the CSRF token", async () => {
    document.cookie = "XSRF-TOKEN=logout-token; path=/";
    const request = vi.fn().mockResolvedValue(null);
    const authApi = createAuthApi({ request } as ApiClient);

    await authApi.logout();

    expect(request).toHaveBeenCalledWith("/auth/logout", {
      method: "POST",
      headers: { "X-XSRF-TOKEN": "logout-token" },
    });
  });
});
