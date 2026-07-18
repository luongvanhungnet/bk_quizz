import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { ApiRequestError } from "../../api/client";
import type { createAuthApi } from "../../auth/api";
import { AuthProvider } from "../../auth/AuthProvider";
import Login from "./Login";

describe("Login", () => {
  it("submits credentials through the auth provider and opens the dashboard", async () => {
    const authenticatedUser = {
      id: "user-1",
      username: "Nguyễn Văn A",
      email: "student@example.com",
      role: "STUDENT" as const,
      emailVerified: true,
      active: true,
    };
    const service = {
      refresh: vi.fn().mockRejectedValue(new Error("No session")),
      login: vi.fn().mockResolvedValue({ accessToken: "token", expiresIn: 300, user: authenticatedUser }),
    } as unknown as ReturnType<typeof createAuthApi>;
    const user = userEvent.setup();

    render(
      <AuthProvider service={service}>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/dashboard" element={<div>Dashboard đã xác thực</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    );

    const email = screen.getByPlaceholderText("mssv@hust.edu.vn");
    const password = screen.getByPlaceholderText("Nhập mật khẩu");
    await user.clear(email);
    await user.type(email, "student@example.com");
    await user.clear(password);
    await user.type(password, "secret123");
    await user.click(screen.getByRole("button", { name: /^Đăng nhập$/i }));

    expect(service.login).toHaveBeenCalledWith({ email: "student@example.com", password: "secret123" });
    expect(await screen.findByText("Dashboard đã xác thực")).toBeInTheDocument();
  });

  it("shows a network error and releases the loading state", async () => {
    const message = "Không thể kết nối đến máy chủ BKQuiz. Vui lòng kiểm tra backend và thử lại.";
    const service = {
      refresh: vi.fn().mockRejectedValue(new Error("No session")),
      login: vi.fn().mockRejectedValue(
        new ApiRequestError(0, {
          success: false,
          message,
          data: null,
          errors: [{ code: "NETWORK_ERROR", message }],
        }),
      ),
    } as unknown as ReturnType<typeof createAuthApi>;
    const user = userEvent.setup();

    render(
      <AuthProvider service={service}>
        <MemoryRouter>
          <Login />
        </MemoryRouter>
      </AuthProvider>,
    );

    await user.type(screen.getByPlaceholderText("mssv@hust.edu.vn"), "student@example.com");
    await user.type(screen.getByPlaceholderText("Nhập mật khẩu"), "Secret123");
    await user.click(screen.getByRole("button", { name: /^Đăng nhập$/i }));

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Đăng nhập$/i })).toBeEnabled();
  });
});
