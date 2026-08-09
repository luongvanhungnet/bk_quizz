import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { BrandLogo } from "./BrandLogo";

describe("BrandLogo", () => {
  it("uses the transparent logo asset without a painted background", () => {
    render(
      <MemoryRouter>
        <BrandLogo />
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: /BKQuiz/i });
    const image = screen.getByRole("img", { name: "BKQuiz" });

    expect(link).toHaveAttribute("href", "/dashboard");
    expect(link.className).not.toMatch(/\bbg-\[/);
    expect(image).toHaveAttribute(
      "src",
      "/brand/bkquiz-logo-transparent.png",
    );
  });
});
