import { createApiClient } from "./client";

describe("createApiClient", () => {
  it("returns page items together with envelope pagination", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      success: true,
      message: "OK",
      data: [{ id: "topic-1" }],
      pagination: { page: 1, limit: 20, totalItems: 1, totalPages: 1, hasNextPage: false, hasPreviousPage: false },
    }), { status: 200, headers: { "Content-Type": "application/json" } })));
    const client = createApiClient({ baseUrl: "/api" });

    await expect(client.requestPage!<{ id: string }>("/topics")).resolves.toEqual({
      items: [{ id: "topic-1" }],
      pagination: { page: 1, limit: 20, totalItems: 1, totalPages: 1, hasNextPage: false, hasPreviousPage: false },
    });
  });

  it("unwraps a successful envelope and sends credentials with the access token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          success: true,
          message: "OK",
          data: { id: "user-1" },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = createApiClient({
      baseUrl: "/api",
      getAccessToken: () => "access-token",
    });

    await expect(client.request<{ id: string }>("/auth/me")).resolves.toEqual({ id: "user-1" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/me",
      expect.objectContaining({
        credentials: "include",
        headers: expect.objectContaining({ Authorization: "Bearer access-token" }),
      }),
    );
  });

  it("rejects a failed envelope with structured error details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            success: false,
            message: "Dữ liệu không hợp lệ",
            data: null,
            errors: [{ code: "VALIDATION_ERROR", field: "email", message: "Email không hợp lệ" }],
            traceId: "trace-123",
          }),
          { status: 422, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    const client = createApiClient({ baseUrl: "/api" });

    await expect(client.request("/auth/register")).rejects.toMatchObject({
      name: "ApiRequestError",
      status: 422,
      code: "VALIDATION_ERROR",
      field: "email",
      message: "Email không hợp lệ",
      traceId: "trace-123",
    });
  });

  it("preserves every validation detail for spreadsheet imports", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      success: false,
      message: "File Excel có dữ liệu không hợp lệ.",
      data: null,
      errors: [
        { code: "QUESTION_TYPE_INVALID", field: "CauHoi!A2", message: "Loại câu hỏi sai." },
        { code: "POINTS_INVALID", field: "CauHoi!J2", message: "Điểm không hợp lệ." },
      ],
      traceId: "excel-trace",
    }), { status: 422, headers: { "Content-Type": "application/json" } })));
    const client = createApiClient({ baseUrl: "/api" });

    const error = await client.request("/quizzes/quiz-1/questions/import").catch((value) => value);

    expect(error).toMatchObject({
      code: "QUESTION_TYPE_INVALID",
      details: [
        { code: "QUESTION_TYPE_INVALID", field: "CauHoi!A2" },
        { code: "POINTS_INVALID", field: "CauHoi!J2" },
      ],
    });
  });

  it("downloads an authenticated binary response without parsing it as JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Uint8Array([80, 75, 3, 4]), {
      status: 200,
      headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient({ baseUrl: "/api", getAccessToken: () => "token" });

    const blob = await client.requestBlob!("/questions/import-template");

    expect(blob.size).toBe(4);
    expect(fetchMock).toHaveBeenCalledWith("/api/questions/import-template", expect.objectContaining({
      credentials: "include",
      headers: expect.objectContaining({ Authorization: "Bearer token" }),
    }));
  });

  it("serializes refresh for concurrent 401 responses and retries with the new token", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const authorization = new Headers(init?.headers).get("Authorization");
      const payload =
        authorization === "Bearer fresh-token"
          ? { success: true, message: "OK", data: { authorized: true } }
          : {
              success: false,
              message: "Phiên đăng nhập đã hết hạn",
              data: null,
              errors: [{ code: "UNAUTHORIZED", message: "Phiên đăng nhập đã hết hạn" }],
            };

      return new Response(JSON.stringify(payload), {
        status: authorization === "Bearer fresh-token" ? 200 : 401,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const refreshAccessToken = vi.fn().mockResolvedValue("fresh-token");
    const client = createApiClient({
      baseUrl: "/api",
      getAccessToken: () => "expired-token",
      refreshAccessToken,
    });

    await expect(
      Promise.all([client.request("/topics"), client.request("/notifications")]),
    ).resolves.toEqual([{ authorized: true }, { authorized: true }]);
    expect(refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("accepts a successful 204 response without trying to parse a body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    const client = createApiClient({ baseUrl: "/api" });

    await expect(client.request<void>("/topics/topic-id", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("reports an empty HTTP error without exposing a JSON parse failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 404 })));
    const client = createApiClient({ baseUrl: "/api" });

    await expect(client.request("/missing")).rejects.toMatchObject({
      name: "ApiRequestError",
      status: 404,
      code: "HTTP_ERROR",
    });
  });

  it("reports a non-JSON response as an invalid API response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("Not Found", { status: 404, headers: { "Content-Type": "text/plain" } })),
    );
    const client = createApiClient({ baseUrl: "/api" });

    await expect(client.request("/missing")).rejects.toMatchObject({
      name: "ApiRequestError",
      status: 404,
      code: "INVALID_API_RESPONSE",
    });
  });

  it("normalizes a fetch failure as a network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const client = createApiClient({ baseUrl: "/api" });

    await expect(client.request("/auth/login")).rejects.toMatchObject({
      name: "ApiRequestError",
      status: 0,
      code: "NETWORK_ERROR",
      message: "Không thể kết nối đến máy chủ BKQuiz. Vui lòng kiểm tra backend và thử lại.",
    });
  });
});
