describe("auth runtime", () => {
  it("does not refresh the session when login returns 401", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          success: false,
          message: "Email hoặc mật khẩu không đúng.",
          data: null,
          errors: [{ code: "UNAUTHORIZED", message: "Email hoặc mật khẩu không đúng." }],
        }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.resetModules();
    const { authService } = await import("./runtime");

    await expect(authService.login({ email: "student@example.com", password: "Wrong123" })).rejects.toMatchObject({
      status: 401,
      code: "UNAUTHORIZED",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
