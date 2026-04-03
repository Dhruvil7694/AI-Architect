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

export interface SignupPayload {
  email: string;
  first_name: string;
  last_name: string;
  password: string;
}

export interface SignupResponse {
  detail: string;
  email: string;
  otp_sent: boolean;
}

export interface OTPRequestPayload {
  email: string;
  purpose: "signup" | "login" | "password_reset";
}

export interface OTPVerifyPayload {
  email: string;
  otp: string;
  purpose: "signup" | "login" | "password_reset";
}

export interface PasswordResetPayload {
  email: string;
  otp: string;
  new_password: string;
}

export interface OTPVerifyResponse {
  detail: string;
  verified: boolean;
  user?: User;
  accessTokenExpiresAt?: string;
}

export async function login(payload: LoginPayload): Promise<LoginResponse> {
  return httpRequest<LoginResponse, LoginPayload>("/api/auth/login/", {
    method: "POST",
    body: payload,
  });
}

export async function signup(payload: SignupPayload): Promise<SignupResponse> {
  return httpRequest<SignupResponse, SignupPayload>("/api/auth/signup/", {
    method: "POST",
    body: payload,
  });
}

export async function requestOTP(payload: OTPRequestPayload): Promise<{ detail: string; email: string }> {
  return httpRequest<{ detail: string; email: string }, OTPRequestPayload>("/api/auth/otp/request/", {
    method: "POST",
    body: payload,
  });
}

export async function verifyOTP(payload: OTPVerifyPayload): Promise<OTPVerifyResponse> {
  return httpRequest<OTPVerifyResponse, OTPVerifyPayload>("/api/auth/otp/verify/", {
    method: "POST",
    body: payload,
  });
}

export async function logout(): Promise<void> {
  await httpRequest<unknown>("/api/auth/logout/", {
    method: "POST",
  });
}

export async function resetPassword(payload: PasswordResetPayload): Promise<{ detail: string }> {
  return httpRequest<{ detail: string }, PasswordResetPayload>("/api/auth/password-reset/", {
    method: "POST",
    body: payload,
  });
}

export async function refreshToken(): Promise<void> {
  await httpRequest<unknown>("/api/auth/refresh/", {
    method: "POST",
  });
}

/** Call before first POST to ensure CSRF cookie is set (e.g. on app load). */
export async function ensureCsrfCookie(): Promise<void> {
  await httpRequest<{ ok: boolean }>("/api/auth/csrf/");
}

export async function getCurrentUser(): Promise<User> {
  return httpRequest<User>("/api/auth/me/");
}
