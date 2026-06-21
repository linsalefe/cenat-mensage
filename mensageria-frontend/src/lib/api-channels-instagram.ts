import { api } from "@/lib/api";
import type {
  Channel,
  InstagramChannelCreate,
  InstagramChannelHealth,
  InstagramChannelUpdate,
  InstagramSendResponse,
} from "@/types/api";

// baseURL já inclui /api → chamar /instagram/* (espelha api-channels-meta.ts).

export async function listInstagramChannels(): Promise<Channel[]> {
  const { data } = await api.get<Channel[]>("/instagram/channels");
  return data;
}

export async function createInstagramChannel(payload: InstagramChannelCreate): Promise<Channel> {
  const { data } = await api.post<Channel>("/instagram/channels", payload);
  return data;
}

export async function updateInstagramChannel(
  id: number,
  payload: InstagramChannelUpdate,
): Promise<Channel> {
  const { data } = await api.patch<Channel>(`/instagram/channels/${id}`, payload);
  return data;
}

export async function deleteInstagramChannel(id: number): Promise<void> {
  await api.delete(`/instagram/channels/${id}`);
}

export async function getInstagramHealth(id: number): Promise<InstagramChannelHealth> {
  const { data } = await api.get<InstagramChannelHealth>(`/instagram/channels/${id}/health`);
  return data;
}

export async function sendInstagramText(
  id: number,
  payload: { to: string; text: string },
): Promise<InstagramSendResponse> {
  const { data } = await api.post<InstagramSendResponse>(
    `/instagram/channels/${id}/send-text`,
    payload,
  );
  return data;
}
