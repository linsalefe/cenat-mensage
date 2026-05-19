"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { formatDistanceToNow, parseISO } from "date-fns";
import { ptBR } from "date-fns/locale";
import axios from "axios";
import { toast } from "sonner";
import { Workflow } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ChatbotFlowListItem } from "@/types/api";

interface Props {
  open: boolean;
  currentFlowId?: number | null;
  onConfirm: (flowId: number) => void;
  onCancel: () => void;
}

function errMsg(err: unknown, fb = "Falha ao carregar fluxos") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fb;
}

function relative(iso: string | null): string {
  if (!iso) return "—";
  try {
    return formatDistanceToNow(parseISO(iso), { locale: ptBR, addSuffix: true });
  } catch {
    return iso;
  }
}

// Backend expõe graph.kind no list. Type não inclui ainda; alarga localmente.
type Flow = ChatbotFlowListItem & { kind?: "chatbot" | "broadcast" };

export function ChatbotFlowSelectDialog({
  open,
  currentFlowId,
  onConfirm,
  onCancel,
}: Props) {
  const [flows, setFlows] = useState<Flow[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get<Flow[]>("/chatbot/flows");
      setFlows(res.data);
    } catch (err) {
      toast.error(errMsg(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      setSelectedId(currentFlowId ?? null);
      load();
    }
  }, [open, currentFlowId, load]);

  const eligible = useMemo(
    () =>
      flows.filter((f) => (f.kind ?? "chatbot") === "chatbot" && f.is_published),
    [flows],
  );

  const empty = !loading && eligible.length === 0;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Associar fluxo de chatbot</DialogTitle>
          <DialogDescription>
            Escolha qual fluxo publicado vai responder neste canal.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="py-8 text-center text-sm text-muted-foreground">
            Carregando…
          </div>
        )}

        {empty && (
          <div className="flex flex-col items-center justify-center gap-3 py-8 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
              <Workflow className="h-6 w-6 text-muted-foreground" />
            </div>
            <div>
              <div className="font-medium">Nenhum fluxo de chatbot publicado</div>
              <div className="mt-1 max-w-xs text-sm text-muted-foreground">
                Crie e publique um fluxo antes de ativar o modo chatbot neste canal.
              </div>
            </div>
          </div>
        )}

        {!loading && !empty && (
          <div className="max-h-72 space-y-2 overflow-auto py-1">
            {eligible.map((f) => {
              const isSelected = f.id === selectedId;
              const isCurrent = f.id === currentFlowId;
              return (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setSelectedId(f.id)}
                  className={cn(
                    "flex w-full items-start gap-3 rounded-md border p-3 text-left transition-colors",
                    isSelected
                      ? "border-emerald-500 bg-emerald-500/5"
                      : "border-border hover:bg-accent/40",
                  )}
                >
                  <div
                    className={cn(
                      "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border",
                      isSelected ? "border-emerald-500" : "border-muted-foreground",
                    )}
                  >
                    {isSelected && (
                      <div className="h-2 w-2 rounded-full bg-emerald-500" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium">{f.name}</span>
                      <Badge variant="outline" className="text-[10px]">
                        v{f.version}
                      </Badge>
                      {isCurrent && (
                        <Badge className="text-[10px]">Atual</Badge>
                      )}
                    </div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      Atualizado {relative(f.updated_at)}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}

        <DialogFooter className="gap-2">
          {empty ? (
            <>
              <Button variant="outline" onClick={onCancel}>
                Cancelar
              </Button>
              <Button asChild>
                <Link href="/workflows" target="_blank">
                  Ir para workflows
                </Link>
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={onCancel}>
                Cancelar
              </Button>
              <Button
                onClick={() => selectedId != null && onConfirm(selectedId)}
                disabled={selectedId == null}
              >
                Confirmar
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
