export interface ApiErrorDetail {
  code: string;
  field?: string;
  message: string;
}

export interface ApiEnvelope<T> {
  success: boolean;
  message: string;
  data: T;
  pagination?: {
    page: number;
    limit: number;
    totalItems: number;
    totalPages: number;
    hasNextPage: boolean;
    hasPreviousPage: boolean;
  };
  errors?: ApiErrorDetail[];
  traceId?: string;
}

export interface ApiClientOptions {
  baseUrl: string;
  getAccessToken?: () => string | null;
  refreshAccessToken?: () => Promise<string | null>;
}

export interface ApiClient {
  request<T>(path: string, init?: RequestInit): Promise<T>;
  requestPage?<T>(path: string, init?: RequestInit): Promise<PaginatedResult<T>>;
  requestBlob?(path: string, init?: RequestInit): Promise<Blob>;
}

export type Pagination = NonNullable<ApiEnvelope<unknown>["pagination"]>;
export interface PaginatedResult<T> { items: T[]; pagination: Pagination; }

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;
  readonly field: string | undefined;
  readonly traceId: string | undefined;
  readonly details: ApiErrorDetail[];

  constructor(status: number, envelope: ApiEnvelope<unknown>) {
    const detail = envelope.errors?.[0];
    super(detail?.message ?? envelope.message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = detail?.code ?? "API_ERROR";
    this.field = detail?.field;
    this.traceId = envelope.traceId;
    this.details = envelope.errors ? [...envelope.errors] : [];
  }
}

export function createApiClient({ baseUrl, getAccessToken, refreshAccessToken }: ApiClientOptions): ApiClient {
  let refreshInFlight: Promise<string | null> | null = null;

  async function send<T>(
    path: string,
    init: RequestInit,
    tokenOverride?: string,
  ): Promise<{ envelope: ApiEnvelope<T>; response: Response }> {
    const headers = Object.fromEntries(new Headers(init.headers).entries());
    const accessToken = tokenOverride ?? getAccessToken?.();

    if (accessToken) {
      headers.Authorization = `Bearer ${accessToken}`;
    }

    const response = await fetch(`${baseUrl.replace(/\/$/, "")}/${path.replace(/^\//, "")}`, {
      ...init,
      credentials: "include",
      headers,
    });
    const body = await response.text();
    if (!body.trim()) {
      return {
        envelope: response.ok
          ? { success: true, message: "", data: undefined as T }
          : {
              success: false,
              message: `Yêu cầu thất bại với mã HTTP ${response.status}.`,
              data: undefined as T,
              errors: [{ code: "HTTP_ERROR", message: `Yêu cầu thất bại với mã HTTP ${response.status}.` }],
            },
        response,
      };
    }
    let envelope: ApiEnvelope<T>;
    try {
      envelope = JSON.parse(body) as ApiEnvelope<T>;
    } catch {
      const message = "Phản hồi từ máy chủ không đúng định dạng JSON.";
      envelope = {
        success: false,
        message,
        data: undefined as T,
        errors: [{ code: "INVALID_API_RESPONSE", message }],
      };
    }

    return { envelope, response };
  }

  async function execute<T>(path: string, init: RequestInit = {}): Promise<ApiEnvelope<T>> {
      try {
        let { envelope, response } = await send<T>(path, init);

        if (response.status === 401 && refreshAccessToken) {
          refreshInFlight ??= refreshAccessToken().finally(() => {
            refreshInFlight = null;
          });
          const freshToken = await refreshInFlight;

          if (freshToken) {
            ({ envelope, response } = await send<T>(path, init, freshToken));
          }
        }

        if (!response.ok || !envelope.success) {
          throw new ApiRequestError(response.status, envelope);
        }

        return envelope;
      } catch (cause) {
        if (cause instanceof ApiRequestError) throw cause;

        const message = "Không thể kết nối đến máy chủ BKQuiz. Vui lòng kiểm tra backend và thử lại.";
        throw new ApiRequestError(0, {
          success: false,
          message,
          data: null,
          errors: [{ code: "NETWORK_ERROR", message }],
        });
      }
    }

  return {
    async request<T>(path: string, init: RequestInit = {}): Promise<T> {
      return (await execute<T>(path, init)).data;
    },
    async requestPage<T>(path: string, init: RequestInit = {}): Promise<PaginatedResult<T>> {
      const envelope = await execute<T[]>(path, init);
      if (!envelope.pagination) {
        throw new ApiRequestError(200, {
          success: false,
          message: "Phản hồi phân trang không chứa thông tin pagination.",
          data: null,
          errors: [{ code: "INVALID_API_RESPONSE", message: "Phản hồi phân trang không chứa thông tin pagination." }],
        });
      }
      return { items: envelope.data, pagination: envelope.pagination };
    },
    async requestBlob(path: string, init: RequestInit = {}): Promise<Blob> {
      const fetchBlob = async (token?: string | null) => {
        const headers = Object.fromEntries(new Headers(init.headers).entries());
        if (token) headers.Authorization = `Bearer ${token}`;
        return fetch(`${baseUrl.replace(/\/$/, "")}/${path.replace(/^\//, "")}`, {
          ...init,
          credentials: "include",
          headers,
        });
      };
      try {
        let response = await fetchBlob(getAccessToken?.());
        if (response.status === 401 && refreshAccessToken) {
          refreshInFlight ??= refreshAccessToken().finally(() => {
            refreshInFlight = null;
          });
          const freshToken = await refreshInFlight;
          if (freshToken) response = await fetchBlob(freshToken);
        }
        if (!response.ok) {
          let envelope: ApiEnvelope<unknown>;
          try {
            envelope = JSON.parse(await response.text()) as ApiEnvelope<unknown>;
          } catch {
            envelope = {
              success: false,
              message: `Không thể tải file mẫu (HTTP ${response.status}).`,
              data: null,
              errors: [{ code: "HTTP_ERROR", message: `Không thể tải file mẫu (HTTP ${response.status}).` }],
            };
          }
          throw new ApiRequestError(response.status, envelope);
        }
        return response.blob();
      } catch (cause) {
        if (cause instanceof ApiRequestError) throw cause;
        const message = "Không thể kết nối đến máy chủ BKQuiz. Vui lòng kiểm tra backend và thử lại.";
        throw new ApiRequestError(0, {
          success: false,
          message,
          data: null,
          errors: [{ code: "NETWORK_ERROR", message }],
        });
      }
    },
  };
}
