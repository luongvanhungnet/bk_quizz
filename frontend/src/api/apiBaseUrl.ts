export interface ApiBaseUrlOptions {
  production: boolean;
  sameOriginProxy: boolean;
}

export function resolveApiBaseUrl(
  configuredValue: string | undefined,
  options: ApiBaseUrlOptions,
): string {
  const baseUrl = configuredValue?.trim() || "/api";

  if (options.production && !options.sameOriginProxy && !baseUrl.startsWith("https://")) {
    throw new Error(
      "VITE_API_BASE_URL phải là URL HTTPS đầy đủ của Spring Cloud Run khi build production. "
        + "Chỉ dùng /api khi đã cấu hình VITE_API_SAME_ORIGIN_PROXY=true và có reverse proxy thực sự.",
    );
  }

  return baseUrl.replace(/\/$/, "");
}
