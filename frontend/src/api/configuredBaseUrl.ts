import { resolveApiBaseUrl } from "./apiBaseUrl";

export const configuredApiBaseUrl = resolveApiBaseUrl(
  import.meta.env.VITE_API_BASE_URL,
  {
    production: import.meta.env.PROD,
    sameOriginProxy: import.meta.env.VITE_API_SAME_ORIGIN_PROXY === "true",
  },
);
