import { api } from "@/lib/api";
import type { EvolutionGroup } from "@/types/api";

export async function fetchGroups(
  instanceName: string,
  getParticipants = false,
  forceRefresh = false,
): Promise<EvolutionGroup[]> {
  const params: Record<string, unknown> = { get_participants: getParticipants };
  if (forceRefresh) params.force_refresh = true;
  const res = await api.get<EvolutionGroup[]>(
    `/evolution/instances/${encodeURIComponent(instanceName)}/groups`,
    { params },
  );
  return res.data;
}
