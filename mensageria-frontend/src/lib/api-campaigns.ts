import { api } from "@/lib/api";

export interface CampaignRun {
  id: number;
  flow_id: number;
  channel_id: number;
  list_id: number | null;
  status: string;
  total_targets: number;
  sessions_created: number;
  sessions_completed: number;
  sessions_failed: number;
  batch_interval_seconds: number;
  daily_limit: number | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
  created_by: number | null;
  error_message: string | null;
}

export interface CampaignMetrics {
  run_id: number;
  sessions_by_status: Record<string, number>;
  messages_by_status: Record<string, number>;
  total_sessions: number;
  delivered: number;
  read: number;
  failed: number;
}

export interface CampaignSession {
  id: number;
  contact_wa_id: string;
  current_node_id: string | null;
  status: string;
  started_at: string | null;
  last_interaction_at: string | null;
  completed_at: string | null;
  variables: Record<string, unknown>;
}

export const campaignsApi = {
  async start(payload: {
    flow_id: number;
    channel_id: number;
    list_id: number;
    batch_interval_seconds?: number;
    daily_limit?: number | null;
  }): Promise<CampaignRun> {
    const { data } = await api.post<CampaignRun>("/campaigns/start", payload);
    return data;
  },
  async list(params: { flow_id?: number; status?: string; limit?: number } = {}): Promise<CampaignRun[]> {
    const { data } = await api.get<CampaignRun[]>("/campaigns", { params });
    return data || [];
  },
  async get(id: number): Promise<CampaignRun> {
    const { data } = await api.get<CampaignRun>(`/campaigns/${id}`);
    return data;
  },
  async cancel(id: number): Promise<CampaignRun> {
    const { data } = await api.post<CampaignRun>(`/campaigns/${id}/cancel`);
    return data;
  },
  async metrics(id: number): Promise<CampaignMetrics> {
    const { data } = await api.get<CampaignMetrics>(`/campaigns/${id}/metrics`);
    return data;
  },
  async sessions(id: number, opts: { limit?: number; offset?: number } = {}): Promise<CampaignSession[]> {
    const { data } = await api.get<CampaignSession[]>(`/campaigns/${id}/sessions`, { params: opts });
    return data || [];
  },
};
