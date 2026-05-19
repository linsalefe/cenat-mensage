"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import axios from "axios";
import { ArrowLeft, Megaphone } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { campaignsApi, type CampaignRun } from "@/lib/api-campaigns";

function errMsg(err: unknown, fallback = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fallback;
}

function statusBadge(status: string) {
  const map: Record<string, string> = {
    pending: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
    running: "bg-blue-500/10 text-blue-700 dark:text-blue-400",
    completed: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
    failed: "bg-red-500/10 text-red-700 dark:text-red-400",
    cancelled: "bg-zinc-500/10 text-zinc-700 dark:text-zinc-400",
  };
  return (
    <Badge variant="outline" className={map[status] || "bg-zinc-500/10"}>
      {status}
    </Badge>
  );
}

export default function CampaignsListPage() {
  const [runs, setRuns] = useState<CampaignRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    campaignsApi
      .list({ limit: 100 })
      .then(setRuns)
      .catch((err) => toast.error(errMsg(err, "Falha ao carregar campanhas")))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <div className="mb-6 flex items-center gap-3">
        <Link href="/workflows">
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Campanhas</h1>
          <p className="text-sm text-muted-foreground">
            Histórico de execuções (campaign runs) — todas as listas disparadas.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="text-sm text-muted-foreground">Carregando…</div>
      ) : runs.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 p-12 text-center">
          <Megaphone className="h-10 w-10 text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">
            Nenhuma campanha rodada ainda — dispare a primeira pelo editor de workflows.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {runs.map((r) => {
            const progress = r.total_targets
              ? Math.round(((r.sessions_created + r.sessions_failed) * 100) / r.total_targets)
              : 0;
            return (
              <Link href={`/workflows/campaigns/${r.id}`} key={r.id}>
                <Card className="cursor-pointer p-4 transition hover:border-foreground/30">
                  <div className="mb-2 flex items-center justify-between">
                    <h2 className="font-medium">Run #{r.id}</h2>
                    {statusBadge(r.status)}
                  </div>
                  <div className="space-y-1 text-xs text-muted-foreground">
                    <div>
                      flow={r.flow_id} · canal={r.channel_id} · lista={r.list_id ?? "—"}
                    </div>
                    <div>
                      criadas {r.sessions_created} / {r.total_targets} • erros {r.sessions_failed}
                    </div>
                  </div>
                  <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div className="h-full bg-blue-500 transition-all" style={{ width: `${progress}%` }} />
                  </div>
                  {r.error_message && (
                    <p className="mt-2 text-[11px] text-red-600 dark:text-red-400">{r.error_message}</p>
                  )}
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
