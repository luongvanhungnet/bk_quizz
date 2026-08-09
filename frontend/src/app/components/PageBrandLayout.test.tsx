import { render, screen } from "@testing-library/react";
import {
  createMemoryRouter,
  RouterProvider,
} from "react-router";
import { describe, expect, it } from "vitest";
import { PageBrandLayout } from "./PageBrandLayout";

describe("PageBrandLayout", () => {
  it("keeps one logo in a normal-flow header instead of overlaying page content", () => {
    const router = createMemoryRouter(
      [
        {
          Component: PageBrandLayout,
          children: [
            {
              path: "/",
              element: <div>Page content</div>,
            },
          ],
        },
      ],
      { initialEntries: ["/"] },
    );

    render(<RouterProvider router={router} />);

    expect(screen.getAllByRole("img", { name: "BKQuiz" })).toHaveLength(1);
    expect(screen.getByRole("banner").className).not.toMatch(
      /\b(fixed|absolute)\b/,
    );
    expect(screen.getByText("Page content")).toBeInTheDocument();
  });
});
