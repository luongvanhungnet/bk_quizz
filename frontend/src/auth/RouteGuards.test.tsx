import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import type { createAuthApi } from "./api";
import { AuthProvider } from "./AuthProvider";
import { GuestOnly, RequireAuth } from "./RouteGuards";

const user = {
  id: "user-1",
  username: "Nguyễn Văn A",
  email: "student@example.com",
  role: "STUDENT" as const,
  emailVerified: true,
  active: true,
};

describe("RequireAuth", () => {
  it("redirects an anonymous visitor to login", async () => {
    const service = {
      refresh: vi.fn().mockRejectedValue(new Error("No session")),
    } as unknown as ReturnType<typeof createAuthApi>;

    render(
      <AuthProvider service={service}>
        <MemoryRouter initialEntries={["/dashboard"]}>
          <Routes>
            <Route element={<RequireAuth />}>
              <Route path="/dashboard" element={<div>Dashboard riêng tư</div>} />
            </Route>
            <Route path="/login" element={<div>Đăng nhập để tiếp tục</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    );

    expect(await screen.findByText("Đăng nhập để tiếp tục")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard riêng tư")).not.toBeInTheDocument();
  });
});

describe("GuestOnly", () => {
  it("redirects an authenticated user away from login", async () => {
    const service = {
      refresh: vi.fn().mockResolvedValue({ accessToken: "token", expiresIn: 300, user }),
    } as unknown as ReturnType<typeof createAuthApi>;

    render(
      <AuthProvider service={service}>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route element={<GuestOnly />}>
              <Route path="/login" element={<div>Biểu mẫu đăng nhập</div>} />
            </Route>
            <Route path="/dashboard" element={<div>Dashboard riêng tư</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    );

    expect(await screen.findByText("Dashboard riêng tư")).toBeInTheDocument();
    expect(screen.queryByText("Biểu mẫu đăng nhập")).not.toBeInTheDocument();
  });
});
