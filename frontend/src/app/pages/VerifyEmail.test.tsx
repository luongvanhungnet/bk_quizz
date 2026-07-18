import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import VerifyEmail from "./VerifyEmail";

const auth = vi.hoisted(() => ({
  verifyEmail: vi.fn(),
  resendVerification: vi.fn(),
  user: { email: "student@example.com" },
}));

vi.mock("../../auth/AuthProvider", () => ({ useAuth: () => auth }));

describe("VerifyEmail", () => {
  it("verifies the token from the link and shows success", async () => {
    auth.verifyEmail.mockResolvedValue(true);

    render(
      <MemoryRouter initialEntries={["/verify-email?token=valid-token"]}>
        <VerifyEmail />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Email đã được xác minh thành công.")).toBeInTheDocument();
    expect(auth.verifyEmail).toHaveBeenCalledWith("valid-token");
    expect(screen.getByRole("link", { name: "Tiếp tục" })).toHaveAttribute("href", "/dashboard");
  });
});
