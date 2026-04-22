import { api } from "@/lib/api";
import type { EvolutionGroup } from "@/types/api";

const CACHE_TTL_MS = 30_000;
const cache = new Map<string, { ts: number; data: EvolutionGroup[] }>();

export async function fetchGroups(
  instanceName: string,
  getParticipants = false,
): Promise<EvolutionGroup[]> {
  const key = `${instanceName}|${getParticipants}`;
  const now = Date.now();
  const cached = cache.get(key);
  if (cached && now - cached.ts < CACHE_TTL_MS) {
    return cached.data;
  }
  const res = await api.get<EvolutionGroup[]>(
    `/evolution/instances/${encodeURIComponent(instanceName)}/groups`,
    { params: { get_participants: getParticipants } },
  );
  cache.set(key, { ts: now, data: res.data });
  return res.data;
}

export function invalidateGroupCache(instanceName?: string): void {
  if (!instanceName) {
    cache.clear();
    return;
  }
  for (const key of Array.from(cache.keys())) {
    if (key.startsWith(`${instanceName}|`)) cache.delete(key);
  }
}
