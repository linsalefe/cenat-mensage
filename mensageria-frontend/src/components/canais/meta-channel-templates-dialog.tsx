"use client";

import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { AlertCircle, FileText, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { templatesApi } from "@/lib/api-templates";
import type { MetaTemplate } from "@/types/api";

interface Props {
  channelId: number | null;
  channelName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function errMsg(err: unknown, fallback = "Erro inesperado") {
  if (axios.isAxiosError(err) && err.response?.data?.detail) {
    const detail = err.response.data.detail;
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  }
  return fallback;
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    APPROVED: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
    PENDING: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
    PENDING_REVIEW: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
    REJECTED: "bg-red-500/10 text-red-700 dark:text-red-400",
    PAUSED: "bg-zinc-500/10 text-zinc-700 dark:text-zinc-400",
    DISABLED: "bg-zinc-500/10 text-zinc-700 dark:text-zinc-400",
  };
  return (
    <Badge variant="outline" className={map[status] || "bg-zinc-500/10"}>
      {status.toLowerCase()}
    </Badge>
  );
}

export function MetaChannelTemplatesDialog({
  channelId,
  channelName,
  open,
  onOpenChange,
}: Props) {
  const [templates, setTemplates] = useState<MetaTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const load = useCallback(async () => {
    if (!channelId) return;
    setLoading(true);
    try {
      const data = await templatesApi.list(channelId);
      setTemplates(data);
    } catch (err) {
      toast.error(errMsg(err, "Erro ao carregar templates"));
    } finally {
      setLoading(false);
    }
  }, [channelId]);

  useEffect(() => {
    if (open && channelId) load();
  }, [open, channelId, load]);

  async function handleSync() {
    if (!channelId) return;
    setSyncing(true);
    try {
      const r = await templatesApi.sync(channelId);
      toast.success(`Sincronizado: ${r.inserted} novos, ${r.updated} atualizados`);
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Erro ao sincronizar"));
    } finally {
      setSyncing(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-4 w-4" /> Templates de {channelName}
          </DialogTitle>
          <DialogDescription>
            Templates aprovados na sua conta Meta. Criação e edição continuam no painel da Meta.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">
            {templates.length}{" "}
            {templates.length === 1 ? "template encontrado" : "templates encontrados"}
          </p>
          <Button onClick={handleSync} disabled={syncing} size="sm" variant="outline">
            <RefreshCw className={syncing ? "mr-2 h-4 w-4 animate-spin" : "mr-2 h-4 w-4"} />
            {syncing ? "Sincronizando…" : "Sincronizar agora"}
          </Button>
        </div>

        <ScrollArea className="h-[400px] rounded-md border">
          {loading ? (
            <div className="p-8 text-center text-sm text-muted-foreground">Carregando…</div>
          ) : templates.length === 0 ? (
            <div className="flex flex-col items-center gap-2 p-8 text-center text-sm text-muted-foreground">
              <AlertCircle className="h-8 w-8 opacity-50" />
              Nenhum template ainda. Clique em "Sincronizar agora" para buscar da Meta.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Idioma</TableHead>
                  <TableHead>Categoria</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {templates.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell className="font-mono text-xs">{t.name}</TableCell>
                    <TableCell className="text-xs">{t.language}</TableCell>
                    <TableCell className="text-xs">
                      {t.category?.toLowerCase() || "—"}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={t.status} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
