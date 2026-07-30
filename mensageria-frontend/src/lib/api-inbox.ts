import { api } from "@/lib/api";
import type { Contact } from "@/types/api";

export interface ContactTag {
  id: number;
  name: string;
  color: string;
}

export interface AssignableUser {
  id: number;
  name: string;
  email: string;
}

/** Espelha VALID_COLORS em app/contact_tags_routes.py. */
export const TAG_COLORS = [
  "blue",
  "green",
  "red",
  "purple",
  "amber",
  "pink",
  "cyan",
] as const;

export const tagColorClasses: Record<string, string> = {
  blue: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  green: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  red: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  purple: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300",
  amber: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  pink: "bg-pink-100 text-pink-700 dark:bg-pink-950 dark:text-pink-300",
  cyan: "bg-cyan-100 text-cyan-700 dark:bg-cyan-950 dark:text-cyan-300",
};

export interface ContactPatch {
  name: string;
  notes: string;
  ai_active: boolean;
  assigned_to: number | null;
}

/** Modo do agente de IA. Só booleano e contagem — a allowlist tem telefones e
 *  nunca é exposta pelo backend. */
export interface AgentStatus {
  sandbox: boolean;
  sandbox_count: number;
  channels_enabled: number[];
}

export const inboxApi = {
  agentStatus: () => api.get<AgentStatus>("/agent/status").then((r) => r.data),

  listTags: () => api.get<ContactTag[]>("/contact-tags").then((r) => r.data),
  createTag: (name: string, color: string) =>
    api.post<ContactTag>("/contact-tags", { name, color }).then((r) => r.data),
  deleteTag: (id: number) => api.delete(`/contact-tags/${id}`).then(() => undefined),

  addTag: (contactId: number, tagId: number) =>
    api.post(`/contacts/${contactId}/tags/${tagId}`).then(() => undefined),
  removeTag: (contactId: number, tagId: number) =>
    api.delete(`/contacts/${contactId}/tags/${tagId}`).then(() => undefined),

  patchContact: (id: number, patch: Partial<ContactPatch>) =>
    api.patch<Contact>(`/contacts/${id}`, patch).then((r) => r.data),
  markRead: (id: number) =>
    api.post(`/contacts/${id}/mark-read`).then(() => undefined),

  createContact: (wa_id: string, name?: string, channel_id?: number | null) =>
    api
      .post<Contact>("/contacts", { wa_id, name, channel_id })
      .then((r) => r.data),

  // Existe separado de usersApi.list porque aquele é admin-only.
  assignableUsers: () =>
    api.get<AssignableUser[]>("/users/assignable").then((r) => r.data),

  uploadMedia: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api
      .post<{ id: number; media_type: string; mime_type: string; filename: string }>(
        "/media/upload",
        fd,
        { headers: { "Content-Type": "multipart/form-data" } },
      )
      .then((r) => r.data);
  },

  /** Só canal oficial: /send-media rejeita evolution/instagram com 404. */
  sendMedia: (
    channelId: number,
    body: {
      to: string;
      media_type: "image" | "document" | "audio" | "video";
      media_id: number;
      caption?: string;
    },
  ) => api.post(`/meta/channels/${channelId}/send-media`, body).then((r) => r.data),

  sendTemplate: (
    channelId: number,
    body: {
      to: string;
      template_name: string;
      language_code: string;
      components?: Array<Record<string, unknown>>;
    },
  ) => api.post(`/meta/channels/${channelId}/send-template`, body).then((r) => r.data),
};

/**
 * Normaliza um telefone digitado para o formato que o WhatsApp espera.
 * 10-11 dígitos = número BR sem código de país; prefixa 55.
 */
export function normalizePhone(raw: string): string {
  const digits = raw.replace(/\D/g, "");
  if (digits.length >= 10 && digits.length <= 11) return `55${digits}`;
  return digits;
}
