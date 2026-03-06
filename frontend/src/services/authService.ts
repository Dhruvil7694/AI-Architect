import { httpRequest } from "./httpClient";

export type Role = "user" | "admin";

export interface User {
  id: string;
  email: string;
  name?: string;
  roles: Role[];
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface LoginResponse {
  user: User;
  accessTokenExpiresAt?: string;
}

export async function login(
  payload: LoginPayload,
): Promise<LoginResponse> {
  return httpRequest<LoginResponse, LoginPayload>("/api/auth/login/", {
    method: "POST",
    body: payload,
  });
}

export async function logout(): Promise<void> {
  await httpRequest<unknown>("/api/auth/logout/", {
    method: "POST",
  });
}

export async function refreshToken(): Promise<void> {
  await httpRequest<unknown>("/api/auth/refresh/", {
    method: "POST",
  });
}

export async function getCurrentUser(): Promise<User> {
  return httpRequest<User>("/api/auth/me/");
}

