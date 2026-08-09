import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MathMarkdown } from "./MathMarkdown";

describe("MathMarkdown", () => {
  it("renders inline LaTeX inside Vietnamese text with KaTeX", () => {
    const { container } = render(
      <MathMarkdown>{"Năng lượng là $E_{a(t)}=\\int_0^T a^2(t)\\,dt$."}</MathMarkdown>,
    );

    expect(container.querySelector(".katex")).not.toBeNull();
    expect(container.textContent).toContain("Năng lượng là");
    const withoutKatex = container.cloneNode(true) as HTMLElement;
    withoutKatex.querySelectorAll(".katex").forEach((node) => node.remove());
    expect(withoutKatex.textContent).not.toContain("\\int");
  });

  it("renders an existing formula that has no dollar delimiters", () => {
    const { container } = render(
      <MathMarkdown normalizeLegacy>{"E_{a(t)} = \\int_{0}^{T} a^2(t)dt"}</MathMarkdown>,
    );

    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("does not execute or render raw HTML", () => {
    const { container } = render(
      <MathMarkdown>{'<script>alert(1)</script><img src=x onerror="alert(2)">'}</MathMarkdown>,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });
});
