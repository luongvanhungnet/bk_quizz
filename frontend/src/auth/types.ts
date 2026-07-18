export type UserRole = "STUDENT" | "TEACHER" | "ADMIN";

export interface UserDto {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  avatarUrl?: string | null;
  bio?: string | null;
  emailVerified: boolean;
  active: boolean;
}

export interface AuthPayload {
  accessToken: string;
  expiresIn: number;
  user: UserDto;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  accountType?: "STUDENT" | "TEACHER";
}

export interface LoginRequest {
  email: string;
  password: string;
}
