"use client";

import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { ListChecks, MoreHorizontal, Pencil, Plus, Trash2, Zap } from "lucide-react";

import { BrandInstagram } from "@/components/brand/channel-icon";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { AutomationDialog } from "@/components/instagram/automation-dialog";
import { ExecutionsDialog } from "@/components/instagram/executions-dialog";
import { listInstagramChannels } from "@/lib/api-channels-instagram";
import {
  listAutomations,
  removeAutomation,
  updateAutomation,
} from "@/lib/api-instagram-automations";
import type { Channel, IgActionType, IgTriggerType, InstagramAutomation } from "@/types/api";

function errMsg(err: unknown, fallback = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fallback;
}

const TRIGGER_LABELS: Record<IgTriggerType, string> = {
  comment: "Comentário",
  dm_received: "DM recebida",
  reaction: "Reação",
  postback: "Ice breaker",
  mention: "Menção",
  story_reply: "Resposta a story",
};

const ACTION_LABELS: Record<IgActionType, string> = {
  send_dm: "Enviar DM",
  private_reply: "Responder no direct",
  public_comment_reply: "Responder no comentário",
};

export default function InstagramAutomacoesPage() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [channelId, setChannelId] = useState<number | null>(null);
  const [automations, setAutomations] = useState<InstagramAutomation[]>([]);
  const [loadingChannels, setLoadingChannels] = useState(true);
  const [loadingList, setLoadingList] = useState(false);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<InstagramAutomation | null>(null);
  const [execTarget, setExecTarget] = useState<InstagramAutomation | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<InstagramAutomation | null>(null);

  const loadChannels = useCallback(async () => {
    setLoadingChannels(true);
    try {
      const chs = await listInstagramChannels();
      setChannels(chs);
      setChannelId((prev) => prev ?? (chs[0]?.id ?? null));
    } catch (err) {
      toast.error(errMsg(err, "Falha ao carregar canais Instagram"));
    } finally {
      setLoadingChannels(false);
    }
  }, []);

  const loadAutomations = useCallback(async (chId: number) => {
    setLoadingList(true);
    try {
      setAutomations(await listAutomations(chId));
    } catch (err) {
      toast.error(errMsg(err, "Falha ao carregar automações"));
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    loadChannels();
  }, [loadChannels]);

  useEffect(() => {
    if (channelId != null) loadAutomations(channelId);
  }, [channelId, loadAutomations]);

  const refresh = () => {
    if (channelId != null) loadAutomations(channelId);
  };

  const openCreate = () => {
    setEditTarget(null);
    setDialogOpen(true);
  };

  const openEdit = (a: InstagramAutomation) => {
    setEditTarget(a);
    setDialogOpen(true);
  };

  const toggleActive = async (a: InstagramAutomation) => {
    try {
      await updateAutomation(a.id, { is_active: !a.is_active });
      setAutomations((prev) =>
        prev.map((x) => (x.id === a.id ? { ...x, is_active: !x.is_active } : x)),
      );
    } catch (err) {
      toast.error(errMsg(err, "Falha ao alterar status"));
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await removeAutomation(deleteTarget.id);
      toast.success("Automação excluída");
      setDeleteTarget(null);
      refresh();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao excluir"));
    }
  };

  const selectedChannel = channels.find((c) => c.id === channelId) || null;

  return (
    <div className="flex flex-col gap-4">
      <div className="mb-2 flex items-start justify-between">
        <div>
          <h1 className="mb-1 flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Zap className="h-6 w-6 text-fuchsia-500" /> Automações do Instagram
          </h1>
          <p className="text-sm text-muted-foreground">
            Regras gatilho → ação: comentou, reagiu, clicou num ice breaker, mencionou…
          </p>
        </div>
        {selectedChannel && (
          <Button onClick={openCreate}>
            <Plus className="mr-2 h-4 w-4" /> Nova automação
          </Button>
        )}
      </div>

      {loadingChannels ? (
        <p className="text-sm text-muted-foreground">Carregando canais…</p>
      ) : channels.length === 0 ? (
        <div className="rounded-md border border-dashed p-8 text-center">
          <BrandInstagram size={32} className="mx-auto mb-2" />
          <p className="text-sm font-medium">Nenhum canal Instagram configurado</p>
          <p className="text-sm text-muted-foreground">
            Crie um canal Instagram em <strong>Canais</strong> para começar a automatizar.
          </p>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Canal:</span>
            <Select
              value={channelId != null ? String(channelId) : ""}
              onValueChange={(v) => setChannelId(Number(v))}
            >
              <SelectTrigger className="w-64">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {channels.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nome</TableHead>
                <TableHead>Gatilho</TableHead>
                <TableHead>Ação</TableHead>
                <TableHead>Prioridade</TableHead>
                <TableHead>Ativa</TableHead>
                <TableHead className="w-16 text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loadingList ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-sm text-muted-foreground">
                    Carregando…
                  </TableCell>
                </TableRow>
              ) : automations.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-sm text-muted-foreground">
                    Nenhuma automação ainda — crie a primeira.
                  </TableCell>
                </TableRow>
              ) : (
                automations.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell className="font-medium">{a.name}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{TRIGGER_LABELS[a.trigger_type]}</Badge>
                    </TableCell>
                    <TableCell className="text-sm">{ACTION_LABELS[a.action_type]}</TableCell>
                    <TableCell className="text-sm tabular-nums">{a.priority}</TableCell>
                    <TableCell>
                      <Switch checked={a.is_active} onCheckedChange={() => toggleActive(a)} />
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button size="sm" variant="ghost">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-44">
                          <DropdownMenuItem onClick={() => openEdit(a)}>
                            <Pencil className="mr-2 h-4 w-4" /> Editar
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => setExecTarget(a)}>
                            <ListChecks className="mr-2 h-4 w-4" /> Execuções
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onClick={() => setDeleteTarget(a)}
                            className="text-destructive focus:text-destructive"
                          >
                            <Trash2 className="mr-2 h-4 w-4" /> Excluir
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </>
      )}

      {channelId != null && (
        <AutomationDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          channelId={channelId}
          automation={editTarget}
          onSuccess={refresh}
        />
      )}

      <ExecutionsDialog
        open={!!execTarget}
        onOpenChange={(o) => !o && setExecTarget(null)}
        automation={execTarget}
      />

      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir automação {deleteTarget?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              A regra para de disparar imediatamente. O histórico de execuções é removido junto.
              <strong> Irreversível.</strong>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
