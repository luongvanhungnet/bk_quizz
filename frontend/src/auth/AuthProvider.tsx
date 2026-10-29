import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { createAuthApi } from "./api";
import { accessTokenStore } from "./accessToken";
import type { AuthPayload, LoginRequest, RegisterRequest, UserDto } from "./types";

export type AuthStatus = "loading" | "authenticated" | "anonymous";
type AuthService = ReturnType<typeof createAuthApi>;

interface AuthContextValue {
  status: AuthStatus;
  user: UserDto | null;
  login(request: LoginRequest): Promise<UserDto>;
  register(request: RegisterRequest): Promise<UserDto>;
  logout(): Promise<void>;
  forgotPassword(email: string): Promise<void>;
  verifyEmail(token: string): Promise<boolean>;
  resendVerification(email: string): Promise<void>;
  setCurrentUser(user: UserDto): void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({
  children,
  service,
}: {
  children: ReactNode;
  service: AuthService;
}) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<UserDto | null>(null);

  function commit(payload: AuthPayload): UserDto {
    accessTokenStore.set(payload.accessToken);
    const enriched = withTokenAuthorities(payload.user, payload.accessToken);
    setUser(enriched);
    setStatus("authenticated");
    return enriched;
  }

  async function login(request: LoginRequest): Promise<UserDto> {
    return commit(await service.login(request));
  }

  async function register(request: RegisterRequest): Promise<UserDto> {
    return commit(await service.register(request));
  }

  async function logout(): Promise<void> {
    try {
      await service.logout();
    } finally {
      accessTokenStore.clear();
      setUser(null);
      setStatus("anonymous");
    }
  }

  async function forgotPassword(email: string): Promise<void> {
    await service.forgotPassword(email);
  }

  async function verifyEmail(token: string): Promise<boolean> {
    const payload = await service.verifyEmail(token);
    if (payload) commit(payload);
    return payload !== null;
  }

  async function resendVerification(email: string): Promise<void> {
    await service.resendVerification(email);
  }

  useEffect(
    () =>
      accessTokenStore.subscribe((token) => {
        if (token === null) {
          setUser(null);
          setStatus("anonymous");
        }
      }),
    [],
  );

  useEffect(() => {
    let active = true;

    void service.refresh().then(
      (payload) => {
        if (!active) return;
        commit(payload);
      },
      () => {
        if (!active) return;
        accessTokenStore.clear();
        setUser(null);
        setStatus("anonymous");
      },
    );

    return () => {
      active = false;
    };
  }, [service]);

  return (
    <AuthContext.Provider value={{ status, user, login, register, logout, forgotPassword,
      verifyEmail, resendVerification, setCurrentUser: setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

function withTokenAuthorities(user: UserDto, token: string): UserDto {
  try {
    const encoded = token.split(".")[1];
    if (!encoded) return user;
    const normalized = encoded.replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "="))) as {
      roles?: unknown; permissions?: unknown;
    };
    const roles = Array.isArray(payload.roles) ? payload.roles.filter((v): v is string => typeof v === "string") : user.administrativeRoles;
    const permissions = Array.isArray(payload.permissions) ? payload.permissions.filter((v): v is string => typeof v === "string") : user.permissions;
    return { ...user, ...(roles ? { administrativeRoles: roles } : {}), ...(permissions ? { permissions } : {}) };
  } catch {
    return user;
  }
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);

  if (!value) {
    throw new Error("useAuth phải được dùng bên trong AuthProvider");
  }

  return value;
}
