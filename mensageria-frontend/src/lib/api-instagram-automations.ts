import { api } from "@/lib/api";
import type {
  InstagramAutomation,
  InstagramAutomationCreate,
  InstagramAutomationExecution,
  InstagramAutomationUpdate,
} from "@/types/api";

export interface ListAutomationsFilters {
  trigger_type?: string;
  active?: boolean;
}

export async function listAutomations(
  channelId: number,
  filters?: ListAutomationsFilters,
): Promise<InstagramAutomation[]> {
  const { data } = await api.get<InstagramAutomation[]>(
    `/instagram/channels/${channelId}/automations`,
    { params: filters },
  );
  return data;
}

export async function createAutomation(
  channelId: number,
  payload: InstagramAutomationCreate,
): Promise<InstagramAutomation> {
  const { data } = await api.post<InstagramAutomation>(
    `/instagram/channels/${channelId}/automations`,
    payload,
  );
  return data;
}

export async function getAutomation(id: number): Promise<InstagramAutomation> {
  const { data } = await api.get<InstagramAutomation>(`/instagram/automations/${id}`);
  return data;
}

export async function updateAutomation(
  id: number,
  patch: InstagramAutomationUpdate,
): Promise<InstagramAutomation> {
  const { data } = await api.patch<InstagramAutomation>(`/instagram/automations/${id}`, patch);
  return data;
}

export async function removeAutomation(id: number): Promise<void> {
  await api.delete(`/instagram/automations/${id}`);
}

export async function listExecutions(
  id: number,
  params?: { limit?: number; offset?: number },
): Promise<InstagramAutomationExecution[]> {
  const { data } = await api.get<InstagramAutomationExecution[]>(
    `/instagram/automations/${id}/executions`,
    { params },
  );
  return data;
}
