"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { ArrowLeft, Ban, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  campaignsApi,
  type CampaignMetrics,
  type CampaignRun,
  type CampaignSession,
} from "@/lib/api-campaigns";

function errMsg(err: unknown, fallback = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fallback;
}

export default function CampaignDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params?.id);

  const [run, setRun] = useState<CampaignRun | null>(null);
  const [metrics, setMetrics] = useState<CampaignMetrics | null>(null);
  const [sessions, setSessions] = useState<CampaignSession[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!Number.isFinite(id)) return;
    setLoading(true);
    try {
      const [r, m, s] = await Promise.all([
        campaignsApi.get(id),
        campaignsApi.metrics(id).catch(() => null),
        campaignsApi.sessions(id, { limit: 100 }).catch(() => []),
      ]);
      setRun(r);
      setMetrics(m);
      setSessions(s);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao carregar"));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCancel() {
    if (!run) return;
    try {
      await campaignsApi.cancel(run.id);
      toast.success("Campanha cancelada");
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao cancelar"));
    }
  }

  if (!Number.isFinite(id)) {
    return <div className="text-sm text-muted-foreground">ID inválido.</div>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => router.push("/workflows/campaigns")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Campanha #{id} {loading && "…"}
            </h1>
            {run && (
              <p className="text-sm text-muted-foreground">
                flow={run.flow_id} · canal={run.channel_id} · lista={run.list_id ?? "—"} · status{" "}
                <Badge variant="outline">{run.status}</Badge>
              </p>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="mr-2 h-4 w-4" /> Atualizar
          </Button>
          {run && (run.status === "pending" || run.status === "running") && (
            <Button variant="destructive" size="sm" onClick={handleCancel}>
              <Ban className="mr-2 h-4 w-4" /> Cancelar
            </Button>
          )}
        </div>
      </div>

      {run && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Metric label="Total" value={run.total_targets} />
          <Metric label="Sessões criadas" value={run.sessions_created} variant="ok" />
          <Metric label="Falhas" value={run.sessions_failed} variant={run.sessions_failed ? "warn" : "muted"} />
          <Metric label="Entregues" value={metrics?.delivered ?? 0} variant="ok" />
        </div>
      )}

      {metrics && (
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-medium">Mensagens por status</h2>
          <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-5">
            {Object.entries(metrics.messages_by_status).map(([k, v]) => (
              <div key={k} className="rounded-md bg-muted/30 p-2 text-center">
                <div className="text-lg font-semibold">{v}</div>
                <div className="text-[10px] uppercase text-muted-foreground">{k}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card className="overflow-hidden">
        <div className="border-b p-3">
          <h2 className="text-sm font-medium">Sessões ({sessions.length})</h2>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Contato</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Nó atual</TableHead>
              <TableHead>Iniciada</TableHead>
              <TableHead>Última interação</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sessions.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-sm text-muted-foreground">
                  Nenhuma sessão ainda.
                </TableCell>
              </TableRow>
            ) : (
              sessions.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-mono text-xs">{s.id}</TableCell>
                  <TableCell className="font-mono text-xs">{s.contact_wa_id}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{s.status}</Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{s.current_node_id || "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {s.started_at ? new Date(s.started_at).toLocaleString("pt-BR") : "—"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {s.last_interaction_at
                      ? new Date(s.last_interaction_at).toLocaleString("pt-BR")
                      : "—"}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>

      <p className="text-xs text-muted-foreground">
        <Link href="/workflows/campaigns" className="underline">
          ← Voltar para campanhas
        </Link>
      </p>
    </div>
  );
}

function Metric({
  label,
  value,
  variant = "muted",
}: {
  label: string;
  value: number;
  variant?: "ok" | "warn" | "muted";
}) {
  const colorMap = {
    ok: "text-emerald-600 dark:text-emerald-400",
    warn: "text-amber-600 dark:text-amber-400",
    muted: "text-foreground",
  };
  return (
    <Card className="p-4">
      <div className={`text-2xl font-semibold ${colorMap[variant]}`}>{value}</div>
      <div className="text-xs uppercase text-muted-foreground">{label}</div>
    </Card>
  );
}
