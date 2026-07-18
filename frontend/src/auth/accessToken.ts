let accessToken: string | null = null;
const listeners = new Set<(token: string | null) => void>();

function notify(): void {
  listeners.forEach((listener) => listener(accessToken));
}

export const accessTokenStore = {
  get(): string | null {
    return accessToken;
  },
  set(token: string): void {
    accessToken = token;
    notify();
  },
  clear(): void {
    accessToken = null;
    notify();
  },
  subscribe(listener: (token: string | null) => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};
