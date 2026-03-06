import { httpRequest } from "./httpClient";
import type { Role, User } from "./authService";

export interface AdminUser extends User {
  isActive: boolean;
}

export interface GetUsersParams {
  search?: string;
  role?: Role;
  limit?: number;
  offset?: number;
}

export interface CreateUserPayload {
  email: string;
  name?: string;
  roles?: Role[];
  password?: string;
}

export interface UpdateUserPayload {
  name?: string;
  roles?: Role[];
  isActive?: boolean;
}

export async function getUsers(
  params: GetUsersParams = {},
): Promise<AdminUser[]> {
  return httpRequest<AdminUser[]>("/api/admin/users/", {
    method: "GET",
    searchParams: params as Record<string, string | number | boolean | undefined>,
  });
}

export async function getUser(id: string): Promise<AdminUser> {
  return httpRequest<AdminUser>(`/api/admin/users/${id}/`, {
    method: "GET",
  });
}

export async function createUser(
  payload: CreateUserPayload,
): Promise<AdminUser> {
  return httpRequest<AdminUser, CreateUserPayload>("/api/admin/users/", {
    method: "POST",
    body: payload,
  });
}

export async function updateUser(
  id: string,
  payload: UpdateUserPayload,
): Promise<AdminUser> {
  return httpRequest<AdminUser, UpdateUserPayload>(
    `/api/admin/users/${id}/`,
    {
      method: "PATCH",
      body: payload,
    },
  );
}

export async function deactivateUser(id: string): Promise<void> {
  await httpRequest<unknown>(`/api/admin/users/${id}/deactivate/`, {
    method: "POST",
  });
}

