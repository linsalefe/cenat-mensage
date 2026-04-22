import { api } from "@/lib/api";
import type { User } from "@/types/api";

export const profileApi = {
  update: (data: { name?: string }) =>
    api.patch<User>("/profile", data).then((r) => r.data),
  changePassword: (data: { current_password: string; new_password: string }) =>
    api.post<{ status: string }>("/profile/change-password", data).then((r) => r.data),
};
