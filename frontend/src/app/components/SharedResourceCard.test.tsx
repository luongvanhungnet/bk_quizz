import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { SharedResourceCard } from "./SharedResourceCard";

describe("SharedResourceCard", () => {
  it("renders a topic preview linked to the read-only classroom route", () => {
    render(
      <MemoryRouter>
        <SharedResourceCard
          classroomId="class-1"
          preview={{
            kind: "TOPIC",
            resourceId: "topic-1",
            referenceId: "share-1",
            title: "Cấu trúc dữ liệu",
            description: "Các cấu trúc dữ liệu nền tảng",
            ownerUsername: "teacher",
            available: true,
            unavailableReason: null,
            quizCount: 3,
            questionCount: 0,
            difficulty: null,
            cognitiveMode: null,
            durationMinutes: null,
            assignmentStatus: null,
            opensAt: null,
            dueAt: null,
            maxAttempts: null,
          }}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("Cấu trúc dữ liệu")).toBeInTheDocument();
    expect(screen.getByText("Các cấu trúc dữ liệu nền tảng")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "/classrooms/class-1/resources/topics/share-1",
    );
  });
});
