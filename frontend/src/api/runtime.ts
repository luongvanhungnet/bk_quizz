import { createAuthApi } from "../auth/api";
import { accessTokenStore } from "../auth/accessToken";
import { createApiClient } from "./client";

const baseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || "/api";
const sessionClient = createApiClient({
  baseUrl,
  getAccessToken: accessTokenStore.get,
});
const sessionAuthApi = createAuthApi(sessionClient);

async function refreshAccessToken(): Promise<string | null> {
  try {
    const payload = await sessionAuthApi.refresh();
    accessTokenStore.set(payload.accessToken);
    return payload.accessToken;
  } catch {
    accessTokenStore.clear();
    return null;
  }
}

export const apiClient = createApiClient({
  baseUrl,
  getAccessToken: accessTokenStore.get,
  refreshAccessToken,
});

export const authService = sessionAuthApi;
