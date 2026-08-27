import { createAuthApi } from "../auth/api";
import { accessTokenStore } from "../auth/accessToken";
import { createApiClient } from "./client";
import { configuredApiBaseUrl } from "./configuredBaseUrl";

const sessionClient = createApiClient({
  baseUrl: configuredApiBaseUrl,
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
  baseUrl: configuredApiBaseUrl,
  getAccessToken: accessTokenStore.get,
  refreshAccessToken,
});

export const authService = sessionAuthApi;
