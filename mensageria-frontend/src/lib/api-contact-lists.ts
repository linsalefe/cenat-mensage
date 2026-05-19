import { api } from "@/lib/api";
import type { ContactList, ContactListMember, CsvImportResult } from "@/types/api";

export const contactListsApi = {
  async list(): Promise<ContactList[]> {
    const { data } = await api.get<ContactList[]>("/contact-lists");
    return data || [];
  },
  async get(id: number): Promise<ContactList> {
    const { data } = await api.get<ContactList>(`/contact-lists/${id}`);
    return data;
  },
  async create(payload: { name: string; description?: string; channel_id?: number }): Promise<ContactList> {
    const { data } = await api.post<ContactList>("/contact-lists", payload);
    return data;
  },
  async update(
    id: number,
    payload: Partial<{ name: string; description: string; channel_id: number | null }>,
  ): Promise<ContactList> {
    const { data } = await api.patch<ContactList>(`/contact-lists/${id}`, payload);
    return data;
  },
  async remove(id: number): Promise<void> {
    await api.delete(`/contact-lists/${id}`);
  },
  async members(
    id: number,
    opts: { limit?: number; offset?: number; search?: string } = {},
  ): Promise<{ members: ContactListMember[] }> {
    const { data } = await api.get<{ members: ContactListMember[] }>(
      `/contact-lists/${id}/members`,
      { params: opts },
    );
    return data || { members: [] };
  },
  async importCsv(id: number, file: File): Promise<CsvImportResult> {
    const form = new FormData();
    form.append("file", file);
    const { data } = await api.post<CsvImportResult>(`/contact-lists/${id}/import`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },
  async removeMember(listId: number, memberId: number): Promise<void> {
    await api.delete(`/contact-lists/${listId}/members/${memberId}`);
  },
};
