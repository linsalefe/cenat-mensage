import { api } from "@/lib/api";

export interface AdminUser {
  id: number;
  email: string;
  name: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

export interface CreateUserPayload {
  email: string;
  password: string;
  name?: string;
  is_admin?: boolean;
}

export interface UpdateUserPayload {
  name?: string;
  is_active?: boolean;
  is_admin?: boolean;
}

export const usersApi = {
  list: () => api.get<AdminUser[]>("/users").then((r) => r.data),
  create: (data: CreateUserPayload) =>
    api.post<AdminUser>("/users", data).then((r) => r.data),
  update: (id: number, data: UpdateUserPayload) =>
    api.patch<AdminUser>(`/users/${id}`, data).then((r) => r.data),
  resetPassword: (id: number, new_password: string) =>
    api
      .post(`/users/${id}/reset-password`, { new_password })
      .then((r) => r.data),
  remove: (id: number) => api.delete(`/users/${id}`).then(() => undefined),
};
