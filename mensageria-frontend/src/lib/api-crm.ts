import { api } from "@/lib/api";
import type { KanbanCard, Pipeline, PipelineColumn } from "@/types/api";

export async function listPipelines(): Promise<Pipeline[]> {
  const { data } = await api.get<Pipeline[]>("/crm/pipelines");
  return data;
}

export async function createPipeline(name: string): Promise<Pipeline> {
  const { data } = await api.post<Pipeline>("/crm/pipelines", { name });
  return data;
}

export async function updatePipeline(
  id: number,
  patch: { name?: string; columns?: PipelineColumn[] },
): Promise<Pipeline> {
  const { data } = await api.patch<Pipeline>(`/crm/pipelines/${id}`, patch);
  return data;
}

export async function deletePipeline(id: number): Promise<void> {
  await api.delete(`/crm/pipelines/${id}`);
}

export interface ColumnInput {
  key?: string;
  label: string;
  color: string;
  order: number;
}

export async function updateColumns(id: number, columns: ColumnInput[]): Promise<Pipeline> {
  const { data } = await api.put<Pipeline>(`/crm/pipelines/${id}/columns`, { columns });
  return data;
}

export async function listKanbanCards(
  pipelineId: number,
  params?: { channel_id?: number; provider?: string },
): Promise<KanbanCard[]> {
  const { data } = await api.get<KanbanCard[]>("/crm/kanban/cards", {
    params: { pipeline_id: pipelineId, ...params },
  });
  return data;
}

export async function moveCard(contactId: number, leadStatus: string): Promise<void> {
  await api.patch(`/crm/kanban/cards/${contactId}/move`, { lead_status: leadStatus });
}

export async function updateCard(
  contactId: number,
  patch: { name?: string; notes?: string; deal_value?: number; lead_status?: string },
): Promise<KanbanCard> {
  const { data } = await api.patch<KanbanCard>(`/crm/kanban/cards/${contactId}`, patch);
  return data;
}
