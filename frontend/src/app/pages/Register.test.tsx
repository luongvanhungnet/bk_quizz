import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import type { createAuthApi } from "../../auth/api";
import { AuthProvider } from "../../auth/AuthProvider";
import Register from "./Register";

describe("Register", () => {
  it("creates only a student-compatible account payload and opens the dashboard", async () => {
    const authenticatedUser = {
      id: "user-1",
      username: "Nguyễn Văn A",
      email: "student@example.com",
      role: "STUDENT" as const,
      emailVerified: false,
      active: true,
    };
    const service = {
      refresh: vi.fn().mockRejectedValue(new Error("No session")),
      register: vi.fn().mockResolvedValue({ accessToken: "token", expiresIn: 300, user: authenticatedUser }),
    } as unknown as ReturnType<typeof createAuthApi>;
    const user = userEvent.setup();

    render(
      <AuthProvider service={service}>
        <MemoryRouter initialEntries={["/register"]}>
          <Routes>
            <Route path="/register" element={<Register />} />
            <Route path="/dashboard" element={<div>Dashboard đã xác thực</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    );

    await user.type(screen.getByPlaceholderText("Nguyễn Văn A"), "Nguyễn Văn A");
    await user.type(screen.getByPlaceholderText("mssv@hust.edu.vn"), "student@example.com");
    await user.type(screen.getByPlaceholderText("Tối thiểu 8 ký tự"), "Secret123");
    await user.type(screen.getByPlaceholderText("Nhập lại"), "Secret123");
    await user.click(screen.getByRole("button", { name: /^Tạo tài khoản$/i }));

    expect(service.register).toHaveBeenCalledWith({
      username: "Nguyễn Văn A",
      email: "student@example.com",
      password: "Secret123",
      accountType: "STUDENT",
    });
    expect(await screen.findByText("Dashboard đã xác thực")).toBeInTheDocument();
  });

  it("rejects a password shorter than the backend minimum", async () => {
    const service = {
      refresh: vi.fn().mockRejectedValue(new Error("No session")),
      register: vi.fn(),
    } as unknown as ReturnType<typeof createAuthApi>;
    const user = userEvent.setup();

    render(
      <AuthProvider service={service}>
        <MemoryRouter>
          <Register />
        </MemoryRouter>
      </AuthProvider>,
    );

    await user.type(screen.getByPlaceholderText("Nguyễn Văn A"), "Nguyễn Văn A");
    await user.type(screen.getByPlaceholderText("mssv@hust.edu.vn"), "student@example.com");
    await user.type(screen.getByPlaceholderText("Tối thiểu 8 ký tự"), "1234567");
    await user.type(screen.getByPlaceholderText("Nhập lại"), "1234567");
    await user.click(screen.getByRole("button", { name: /^Tạo tài khoản$/i }));

    expect(service.register).not.toHaveBeenCalled();
    expect(screen.getByText(/mật khẩu tối thiểu 8 ký tự/i)).toBeInTheDocument();
  });

  it("rejects a password that does not contain uppercase, lowercase and a number", async () => {
    const service = {
      refresh: vi.fn().mockRejectedValue(new Error("No session")),
      register: vi.fn(),
    } as unknown as ReturnType<typeof createAuthApi>;
    const user = userEvent.setup();

    render(
      <AuthProvider service={service}>
        <MemoryRouter>
          <Register />
        </MemoryRouter>
      </AuthProvider>,
    );

    await user.type(screen.getByPlaceholderText("Nguyễn Văn A"), "Nguyễn Văn A");
    await user.type(screen.getByPlaceholderText("mssv@hust.edu.vn"), "student@example.com");
    await user.type(screen.getByPlaceholderText("Tối thiểu 8 ký tự"), "secret123");
    await user.type(screen.getByPlaceholderText("Nhập lại"), "secret123");
    await user.click(screen.getByRole("button", { name: /^Tạo tài khoản$/i }));

    expect(service.register).not.toHaveBeenCalled();
    expect(screen.getByText(/chữ thường, chữ hoa và chữ số/i)).toBeInTheDocument();
  });
});
