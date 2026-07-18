import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import Dashboard from "./Dashboard";

const api = vi.hoisted(() => ({
  topics: vi.fn(),
  dashboard: vi.fn(),
  profile: vi.fn(),
  preferences: vi.fn(),
  deleteTopic: vi.fn(),
  saveTopic: vi.fn(),
  unsaveTopic: vi.fn(),
}));

vi.mock("../../api/bkquiz", () => ({ bkquizApi: api }));
vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({
    user: { id: "user-1", username: "Sinh viên", email: "student@example.com" },
    logout: vi.fn(),
    setCurrentUser: vi.fn(),
  }),
}));

describe("Dashboard", () => {
  beforeEach(() => {
    api.topics.mockReset();
    api.dashboard.mockReset();
  });

  it("keeps real topics visible when the dashboard summary request fails", async () => {
    api.topics.mockResolvedValue({
      items: [{
        id: "topic-1",
        ownerId: "user-1",
        title: "Mạng máy tính",
        description: "TCP/IP",
        visibility: "PRIVATE",
        status: "DRAFT",
        publishedAt: null,
        createdAt: "2026-07-16T00:00:00Z",
        updatedAt: "2026-07-16T00:00:00Z",
        version: 0,
      }],
      pagination: { page: 1, limit: 100, totalItems: 1, totalPages: 1, hasNextPage: false, hasPreviousPage: false },
    });
    api.dashboard.mockRejectedValue(Object.assign(new Error("Không thể tải thống kê."), { traceId: "trace-dashboard-500" }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(<QueryClientProvider client={client}><MemoryRouter><Dashboard /></MemoryRouter></QueryClientProvider>);

    expect(await screen.findByText("Mạng máy tính")).toBeInTheDocument();
    expect(screen.getByText("Không thể tải thống kê.")).toBeInTheDocument();
    expect(screen.getByText(/trace-dashboard-500/)).toBeInTheDocument();
  });

  it("retries only the dashboard summary query", async () => {
    api.topics.mockResolvedValue({ items: [], pagination: { page: 1, limit: 100, totalItems: 0, totalPages: 0, hasNextPage: false, hasPreviousPage: false } });
    api.dashboard
      .mockRejectedValueOnce(new Error("Không thể tải thống kê."))
      .mockResolvedValueOnce({
        stats: { topicCount: 0, quizCount: 0, submittedAttemptCount: 0, averagePercentage: 0 },
        recentTopics: [],
        recentActivities: [],
      });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter><Dashboard /></MemoryRouter></QueryClientProvider>);

    fireEvent.click(await screen.findByRole("button", { name: "Thử lại" }));

    expect(await screen.findByText("Điểm trung bình")).toBeInTheDocument();
    expect(api.dashboard).toHaveBeenCalledTimes(2);
    expect(api.topics).toHaveBeenCalledTimes(1);
  });
});
