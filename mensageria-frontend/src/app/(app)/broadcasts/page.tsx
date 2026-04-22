"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { format, parseISO } from "date-fns";
import { ptBR } from "date-fns/locale";
import axios from "axios";
import { toast } from "sonner";
import { Send, RefreshCw, X as XIcon } from "lucide-react";

import { api } from "@/lib/api";
import { broadcastsApi } from "@/lib/api-broadcasts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import type {
  BroadcastJob, BroadcastLog, BroadcastStatus, Channel,
} from "@/types/api";

function errMsg(err: unknown, fb = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fb;
}

function fmt(s: string | null) {
  if (!s) return "—";
  try {
    return format(parseISO(s), "dd/MM/yy HH:mm", { locale: ptBR });
  } catch {
    return s;
  }
}

const TAB_ORDER: { value: BroadcastStatus; label: string }[] = [
  { value: "pending", label: "Pendentes" },
  { value: "running", label: "Executando" },
  { value: "completed", label: "Concluídos" },
  { value: "cancelled", label: "Cancelados" },
  { value: "failed", label: "Falhos" },
];

function statusBadgeColor(s: BroadcastStatus) {
  switch (s) {
    case "pending": return "bg-amber-500/10 text-amber-700 dark:text-amber-400";
    case "running": return "bg-blue-500/10 text-blue-700 dark:text-blue-400";
    case "completed": return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400";
    case "cancelled": return "bg-muted text-muted-foreground";
    case "failed": return "bg-rose-500/10 text-rose-700 dark:text-rose-400";
  }
}

export default function BroadcastsPage() {
  const [tab, setTab] = useState<BroadcastStatus>("pending");
  const [jobs, setJobs] = useState<BroadcastJob[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [channelFilter, setChannelFilter] = useState<string>("all");
  const [search, setSearch] = useState("");

  const [detailJob, setDetailJob] = useState<BroadcastJob | null>(null);
  const [detailLogs, setDetailLogs] = useState<BroadcastLog[]>([]);
  const [loadingLogs, setLoadingLogs] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [jobsRes, chRes] = await Promise.all([
        broadcastsApi.list({
          status: tab,
          channel_id:
            channelFilter !== "all" ? Number(channelFilter) : undefined,
          limit: 100,
        }),
        api.get<Channel[]>("/chatbot/channels"),
      ]);
      setJobs(jobsRes);
      setChannels(chRes.data);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao carregar"));
    } finally {
      setLoading(false);
    }
  }, [tab, channelFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const filteredJobs = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return jobs;
    return jobs.filter((j) => j.name.toLowerCase().includes(q));
  }, [jobs, search]);

  const openDetail = async (job: BroadcastJob) => {
    setDetailJob(job);
    setDetailLogs([]);
    setLoadingLogs(true);
    try {
      const logs = await broadcastsApi.getLogs(job.id, 100, 0);
      setDetailLogs(logs);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao carregar logs"));
    } finally {
      setLoadingLogs(false);
    }
  };

  const cancelJob = async (job: BroadcastJob) => {
    if (!confirm(`Cancelar broadcast "${job.name}"?`)) return;
    try {
      await broadcastsApi.cancel(job.id);
      toast.success("Cancelado");
      load();
    } catch (err) {
      toast.error(errMsg(err));
    }
  };

  const removeJob = async (job: BroadcastJob) => {
    if (!confirm(`Excluir broadcast "${job.name}"?`)) return;
    try {
      await broadcastsApi.remove(job.id);
      toast.success("Excluído");
      load();
    } catch (err) {
      toast.error(errMsg(err));
    }
  };

  const channelName = (id: number) =>
    channels.find((c) => c.id === id)?.name || `Canal #${id}`;

  const audienceSummary = (j: BroadcastJob) => {
    const s = j.audience_spec || {};
    switch (j.audience_type) {
      case "all_groups": return "Todos os grupos";
      case "selected_groups":
        return `${(s.group_ids || []).length} grupo(s)`;
      case "contacts_tag":
        return `Tag: ${s.tag || "?"}`;
      case "csv":
        return `CSV (${(s.contacts || []).length})`;
      case "single_contact":
        return s.wa_id || "Contato";
      default:
        return j.audience_type;
    }
  };

  const downloadCsv = () => {
    if (!detailJob) return;
    const rows = [
      ["target_wa_id", "target_name", "status", "error_detail", "sent_at"],
      ...detailLogs.map((l) => [
        l.target_wa_id,
        l.target_name || "",
        l.status,
        (l.error_detail || "").replace(/\n/g, " "),
        l.sent_at || "",
      ]),
    ];
    const csv = rows
      .map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `broadcast-${detailJob.id}-logs.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Send className="h-5 w-5" /> Broadcasts
        </h1>
        <Button size="sm" variant="outline" onClick={load}>
          <RefreshCw className="h-3 w-3 mr-1" /> Atualizar
        </Button>
      </div>

      <div className="flex items-center gap-3">
        <Select value={channelFilter} onValueChange={setChannelFilter}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Todos os canais" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos os canais</SelectItem>
            {channels.map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          className="max-w-sm"
          placeholder="Buscar por nome…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as BroadcastStatus)}>
        <TabsList>
          {TAB_ORDER.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>{t.label}</TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nome</TableHead>
            <TableHead>Canal</TableHead>
            <TableHead>Audiência</TableHead>
            <TableHead>Agendado</TableHead>
            <TableHead>Progresso</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Ações</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-sm text-muted-foreground">
                Carregando…
              </TableCell>
            </TableRow>
          ) : filteredJobs.length === 0 ? (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-sm text-muted-foreground">
                Sem broadcasts nesta aba.
              </TableCell>
            </TableRow>
          ) : (
            filteredJobs.map((j) => (
              <TableRow
                key={j.id}
                className="cursor-pointer"
                onClick={() => openDetail(j)}
              >
                <TableCell>{j.name}</TableCell>
                <TableCell>{channelName(j.channel_id)}</TableCell>
                <TableCell>
                  <Badge variant="outline">{audienceSummary(j)}</Badge>
                </TableCell>
                <TableCell>{fmt(j.scheduled_at) === "—" ? <span className="text-muted-foreground text-xs">imediato</span> : fmt(j.scheduled_at)}</TableCell>
                <TableCell className="font-mono text-xs">
                  {j.sent_count + j.error_count}/{j.total_targets}
                </TableCell>
                <TableCell>
                  <span className={`inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded ${statusBadgeColor(j.status)}`}>
                    {j.status}
                  </span>
                </TableCell>
                <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                  <div className="flex justify-end gap-1">
                    {(j.status === "pending" || j.status === "running") && (
                      <Button size="sm" variant="outline" onClick={() => cancelJob(j)}>
                        Cancelar
                      </Button>
                    )}
                    <Button size="sm" variant="destructive" onClick={() => removeJob(j)}>
                      Excluir
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      <Dialog open={!!detailJob} onOpenChange={(open) => !open && setDetailJob(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>
              {detailJob?.name}
              <div className="text-xs font-normal text-muted-foreground">
                id={detailJob?.id} · status={detailJob?.status}
              </div>
            </DialogTitle>
          </DialogHeader>
          {detailJob && (
            <div className="space-y-4">
              <div className="grid grid-cols-4 gap-3 text-center">
                <div className="rounded border p-3">
                  <div className="text-xl font-semibold">{detailJob.total_targets}</div>
                  <div className="text-xs text-muted-foreground">Total</div>
                </div>
                <div className="rounded border p-3">
                  <div className="text-xl font-semibold text-emerald-600">{detailJob.sent_count}</div>
                  <div className="text-xs text-muted-foreground">Enviados</div>
                </div>
                <div className="rounded border p-3">
                  <div className="text-xl font-semibold text-rose-600">{detailJob.error_count}</div>
                  <div className="text-xs text-muted-foreground">Erros</div>
                </div>
                <div className="rounded border p-3">
                  <div className="text-xs font-mono">{detailJob.interval_seconds}s</div>
                  <div className="text-xs text-muted-foreground">Intervalo</div>
                </div>
              </div>

              <div className="text-xs text-muted-foreground">
                Agendado: {fmt(detailJob.scheduled_at)} ·
                Iniciado: {fmt(detailJob.started_at)} ·
                Concluído: {fmt(detailJob.completed_at)}
              </div>

              {detailJob.error_message && (
                <div className="rounded border border-rose-500/30 bg-rose-500/5 p-2 text-xs">
                  {detailJob.error_message}
                </div>
              )}

              <div className="flex items-center justify-between">
                <div className="text-sm font-medium">Logs ({detailLogs.length})</div>
                <Button size="sm" variant="outline" onClick={downloadCsv}>
                  Baixar CSV
                </Button>
              </div>

              <div className="max-h-64 overflow-auto rounded border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Destinatário</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Quando</TableHead>
                      <TableHead>Erro</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loadingLogs ? (
                      <TableRow>
                        <TableCell colSpan={4} className="text-center text-xs text-muted-foreground">
                          Carregando logs…
                        </TableCell>
                      </TableRow>
                    ) : detailLogs.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={4} className="text-center text-xs text-muted-foreground">
                          Sem logs ainda.
                        </TableCell>
                      </TableRow>
                    ) : (
                      detailLogs.map((l) => (
                        <TableRow key={l.id}>
                          <TableCell className="font-mono text-xs">
                            {l.target_name || l.target_wa_id}
                          </TableCell>
                          <TableCell>
                            <Badge variant={l.status === "sent" ? "default" : "destructive"}>
                              {l.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs">{fmt(l.sent_at)}</TableCell>
                          <TableCell className="text-xs text-rose-600 truncate max-w-xs">
                            {l.error_detail || ""}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
