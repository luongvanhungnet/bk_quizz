import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmailVerificationAction } from "./EmailVerificationAction";

it("lets an unverified user request a verification email", async () => {
  const resend = vi.fn().mockResolvedValue(undefined);
  render(<EmailVerificationAction email="student@example.com" onResend={resend} />);

  await userEvent.click(screen.getByRole("button", { name: "Gửi email xác thực" }));

  expect(resend).toHaveBeenCalledWith("student@example.com");
  expect(await screen.findByText("Email xác thực đã được xếp hàng gửi.")).toBeInTheDocument();
});
