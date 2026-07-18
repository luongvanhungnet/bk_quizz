import type { ApiClient } from "../api/client";
import type { AuthPayload, LoginRequest, RegisterRequest } from "./types";

function jsonBody(value: unknown): Pick<RequestInit, "body" | "headers"> {
  return {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(value),
  };
}

function csrfHeaders(): Record<string, string> {
  const prefix = "XSRF-TOKEN=";
  const cookie = document.cookie.split("; ").find((value) => value.startsWith(prefix));

  return cookie ? { "X-XSRF-TOKEN": decodeURIComponent(cookie.slice(prefix.length)) } : {};
}

export function createAuthApi(client: Pick<ApiClient, "request">) {
  const api = {
    async verifyEmail(token: string): Promise<AuthPayload | null> {
      await client.request<null>("/auth/verify-email", {
        method: "POST",
        ...jsonBody({ token }),
      });
      try {
        return await api.refresh();
      } catch {
        return null;
      }
    },
    resendVerification(email: string): Promise<null> {
      return client.request<null>("/auth/verify-email/resend", {
        method: "POST",
        ...jsonBody({ email }),
      });
    },
    forgotPassword(email: string): Promise<null> {
      return client.request<null>("/auth/forgot-password", {
        method: "POST",
        ...jsonBody({ email }),
      });
    },
    login(request: LoginRequest): Promise<AuthPayload> {
      return client.request<AuthPayload>("/auth/login", {
        method: "POST",
        ...jsonBody(request),
      });
    },
    logout(): Promise<null> {
      return client.request<null>("/auth/logout", {
        method: "POST",
        headers: csrfHeaders(),
      });
    },
    register(request: RegisterRequest): Promise<AuthPayload> {
      return client.request<AuthPayload>("/auth/register", {
        method: "POST",
        ...jsonBody(request),
      });
    },
    refresh(): Promise<AuthPayload> {
      return client.request<AuthPayload>("/auth/refresh-token", {
        method: "POST",
        headers: csrfHeaders(),
      });
    },
  };
  return api;
}
