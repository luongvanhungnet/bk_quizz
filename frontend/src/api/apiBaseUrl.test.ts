import { resolveApiBaseUrl } from "./apiBaseUrl";

describe("resolveApiBaseUrl", () => {
  it("rejects the development /api fallback in a production build without a same-origin proxy", () => {
    expect(() => resolveApiBaseUrl("/api", { production: true, sameOriginProxy: false }))
      .toThrow("VITE_API_BASE_URL");
  });
});
