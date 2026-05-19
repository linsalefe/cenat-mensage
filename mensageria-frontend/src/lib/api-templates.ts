import { api } from "@/lib/api";
import type { MetaTemplate } from "@/types/api";

export interface TemplateSyncResponse {
  channel_id: number;
  total_remote: number;
  inserted: number;
  updated: number;
}

export const templatesApi = {
  async sync(channelId: number): Promise<TemplateSyncResponse> {
    const { data } = await api.post<TemplateSyncResponse>(
      `/meta/channels/${channelId}/templates/sync`,
    );
    return data;
  },
  async list(channelId: number, status?: string): Promise<MetaTemplate[]> {
    const params = status ? { status } : undefined;
    const { data } = await api.get<MetaTemplate[]>(
      `/meta/channels/${channelId}/templates`,
      { params },
    );
    return data || [];
  },
};
