import { api } from "@/lib/api";
import type { BroadcastJob, BroadcastLog, BroadcastStatus } from "@/types/api";

export interface CreateBroadcastPayload {
  name: string;
  channel_id: number;
  audience_type: BroadcastJob["audience_type"];
  audience_spec: Record<string, any>;
  message_payload: {
    text?: string;
    media_id?: number;
    caption?: string;
  };
  flow_id?: number | null;
  interval_seconds?: number;
  scheduled_at?: string | null;
}

export interface ListParams {
  status?: BroadcastStatus;
  channel_id?: number;
  limit?: number;
  offset?: number;
}

export const broadcastsApi = {
  list: (params?: ListParams) =>
    api.get<BroadcastJob[]>("/broadcasts", { params }).then((r) => r.data),
  get: (id: number) => api.get<BroadcastJob>(`/broadcasts/${id}`).then((r) => r.data),
  create: (data: CreateBroadcastPayload) =>
    api.post<BroadcastJob>("/broadcasts", data).then((r) => r.data),
  cancel: (id: number) =>
    api.post<BroadcastJob>(`/broadcasts/${id}/cancel`).then((r) => r.data),
  remove: (id: number) => api.delete(`/broadcasts/${id}`).then(() => undefined),
  getLogs: (id: number, limit = 100, offset = 0) =>
    api
      .get<BroadcastLog[]>(`/broadcasts/${id}/logs`, { params: { limit, offset } })
      .then((r) => r.data),
};
