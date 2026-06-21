"use client";

import { useEffect, useState } from "react";
import { format, parseISO } from "date-fns";
import { ptBR } from "date-fns/locale";

import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listExecutions } from "@/lib/api-instagram-automations";
import type { InstagramAutomation, InstagramAutomationExecution } from "@/types/api";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  automation: InstagramAutomation | null;
}

function fmt(s: string | null) {
  if (!s) return "—";
  try {
    return format(parseISO(s), "dd/MM HH:mm", { locale: ptBR });
  } catch {
    return s;
  }
}

function StatusBadge({ status }: { status: InstagramAutomationExecution["status"] }) {
  if (status === "sent")
    return (
      <Badge className="border-transparent bg-emerald-500/15 text-emerald-600 hover:bg-emerald-500/15 dark:text-emerald-400">
        enviado
      </Badge>
    );
  if (status === "skipped")
    return <Badge variant="secondary">pulado</Badge>;
  return (
    <Badge className="border-transparent bg-red-500/15 text-red-600 hover:bg-red-500/15 dark:text-red-400">
      erro
    </Badge>
  );
}

export function ExecutionsDialog({ open, onOpenChange, automation }: Props) {
  const [rows, setRows] = useState<InstagramAutomationExecution[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !automation) return;
    let cancelled = false;
    setLoading(true);
    listExecutions(automation.id, { limit: 100 })
      .then((data) => {
        if (!cancelled) setRows(data);
      })
      .catch(() => {
        if (!cancelled) setRows([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, automation]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Execuções — {automation?.name}</DialogTitle>
        </DialogHeader>

        {loading ? (
          <p className="py-6 text-center text-sm text-muted-foreground">Carregando…</p>
        ) : rows.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Nenhuma execução ainda — dispara quando chegar um evento real.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Quando</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Contato/ref</TableHead>
                <TableHead>Detalhe</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="whitespace-nowrap text-xs">{fmt(e.created_at)}</TableCell>
                  <TableCell>
                    <StatusBadge status={e.status} />
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {e.contact_wa_id || e.trigger_ref}
                  </TableCell>
                  <TableCell className="max-w-[260px] break-words text-xs text-muted-foreground">
                    {e.detail || "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DialogContent>
    </Dialog>
  );
}
