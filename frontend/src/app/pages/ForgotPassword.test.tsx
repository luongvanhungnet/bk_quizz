import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import type { createAuthApi } from "../../auth/api";
import { AuthProvider } from "../../auth/AuthProvider";
import ForgotPassword from "./ForgotPassword";

describe("ForgotPassword", () => {
  it("requests a reset link through the backend and shows the neutral confirmation", async () => {
    const service = {
      refresh: vi.fn().mockRejectedValue(new Error("No session")),
      forgotPassword: vi.fn().mockResolvedValue(null),
    } as unknown as ReturnType<typeof createAuthApi>;
    const user = userEvent.setup();

    render(
      <AuthProvider service={service}>
        <MemoryRouter>
          <ForgotPassword />
        </MemoryRouter>
      </AuthProvider>,
    );

    await user.type(screen.getByPlaceholderText("mssv@hust.edu.vn"), "student@example.com");
    await user.click(screen.getByRole("button", { name: /Gửi link đặt lại/i }));

    expect(service.forgotPassword).toHaveBeenCalledWith("student@example.com");
    expect(await screen.findByRole("heading", { name: "Đã gửi email" })).toBeInTheDocument();
  });
});
