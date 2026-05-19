import { api } from "@/lib/api";
import type {
  Channel,
  MetaChannelCreate,
  MetaChannelHealth,
  MetaChannelUpdate,
  MetaSendResponse,
  MetaSendTemplateRequest,
  MetaSendTextRequest,
} from "@/types/api";

export async function listMetaChannels(): Promise<Channel[]> {
  const { data } = await api.get<Channel[]>("/meta/channels");
  return data;
}

export async function createMetaChannel(payload: MetaChannelCreate): Promise<Channel> {
  const { data } = await api.post<Channel>("/meta/channels", payload);
  return data;
}

export async function updateMetaChannel(id: number, payload: MetaChannelUpdate): Promise<Channel> {
  const { data } = await api.patch<Channel>(`/meta/channels/${id}`, payload);
  return data;
}

export async function deleteMetaChannel(id: number): Promise<void> {
  await api.delete(`/meta/channels/${id}`);
}

export async function getMetaChannelHealth(id: number): Promise<MetaChannelHealth> {
  const { data } = await api.get<MetaChannelHealth>(`/meta/channels/${id}/health`);
  return data;
}

export async function sendMetaText(id: number, payload: MetaSendTextRequest): Promise<MetaSendResponse> {
  const { data } = await api.post<MetaSendResponse>(`/meta/channels/${id}/send-text`, payload);
  return data;
}

export async function sendMetaTemplate(id: number, payload: MetaSendTemplateRequest): Promise<MetaSendResponse> {
  const { data } = await api.post<MetaSendResponse>(`/meta/channels/${id}/send-template`, payload);
  return data;
}
