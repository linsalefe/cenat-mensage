"use client";

import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  MoreHorizontal,
  QrCode,
  RefreshCw,
  Pencil,
  Power,
  Trash2,
} from "lucide-react";

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
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  Channel,
  ChatbotFlowListItem,
  ConnectionStatus,
} from "@/types/api";

function errMsg(err: unknown, fallback = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fallback;
}

/** 553195176902@s.whatsapp.net → +55 31 9517-6902; 5515997567886 → +55 15 99756-7886 */
function formatWaId(raw: string | null | undefined): string {
  if (!raw) return "—";
  const digits = String(raw).split("@")[0].replace(/\D/g, "");
  if (digits.length < 10) return raw;
  const country = digits.startsWith("55") ? digits.slice(0, 2) : "";
  const rest = country ? digits.slice(2) : digits;
  const ddd = rest.slice(0, 2);
  const phone = rest.slice(2);
  const p1 = phone.length > 8 ? phone.slice(0, phone.length - 4) : phone.slice(0, -4);
  const p2 = phone.slice(-4);
  return `${country ? "+" + country + " " : ""}${ddd} ${p1}-${p2}`;
}

function statusBadge(s: ConnectionStatus | undefined) {
  const base = "px-2 py-0.5 rounded-full text-xs font-medium";
  switch (s) {
    case "open":
      return { label: "conectado", cls: `${base} bg-emerald-500/15 text-emerald-600 dark:text-emerald-400` };
    case "close":
      return { label: "desconectado", cls: `${base} bg-red-500/15 text-red-600 dark:text-red-400` };
    case "connecting":
      return { label: "conectando", cls: `${base} bg-amber-500/15 text-amber-600 dark:text-amber-400` };
    default:
      return { label: "desconhecido", cls: `${base} bg-zinc-500/15 text-zinc-500` };
  }
}

export default function CanaisPage() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [flows, setFlows] = useState<ChatbotFlowListItem[]>([]);
  const [loading, setLoading] = useState(true);

  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPurpose, setNewPurpose] = useState("commercial");
  const [creating, setCreating] = useState(false);

  const [qrOpen, setQrOpen] = useState(false);
  const [qrData, setQrData] = useState<string | null>(null);
  const [qrTitle, setQrTitle] = useState("");

  const [editTarget, setEditTarget] = useState<Channel | null>(null);
  const [eName, setEName] = useState("");
  const [ePhone, setEPhone] = useState("");
  const [eMode, setEMode] = useState<Channel["operation_mode"]>("none");
  const [saving, setSaving] = useState(false);

  const [logoutTarget, setLogoutTarget] = useState<Channel | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Channel | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [chRes, flowsRes] = await Promise.all([
        api.get<Channel[]>("/chatbot/channels"),
        api.get<ChatbotFlowListItem[]>("/chatbot/flows"),
      ]);
      setChannels(chRes.data);
      setFlows(flowsRes.data);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao carregar canais"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const refreshRow = async (c: Channel) => {
    if (!c.instance_name) return;
    try {
      const res = await api.get(`/evolution/instances/${c.instance_name}/status`);
      const state = (res.data?.state || "").toLowerCase();
      const cs: ConnectionStatus =
        state === "open" || state === "close" || state === "connecting"
          ? (state as ConnectionStatus)
          : "unknown";
      setChannels((prev) =>
        prev.map((x) =>
          x.id === c.id
            ? { ...x, connection_status: cs, is_connected: cs === "open" }
            : x,
        ),
      );
      toast.success(`${c.name}: ${cs}`);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao consultar status"));
    }
  };

  const createInstance = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const res = await api.post("/evolution/instances", {
        name: newName,
        purpose: newPurpose,
      });
      toast.success("Instância criada");
      setCreateOpen(false);
      setNewName("");
      if (res.data.qrcode?.base64) {
        setQrData(res.data.qrcode.base64);
        setQrTitle(res.data.instance_name);
        setQrOpen(true);
      }
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao criar instância"));
    } finally {
      setCreating(false);
    }
  };

  const showQR = async (c: Channel) => {
    if (!c.instance_name) return;
    try {
      const res = await api.get(`/evolution/instances/${c.instance_name}/qrcode`);
      const b64 = res.data?.base64 || res.data?.qrcode?.base64 || null;
      if (!b64) {
        toast.info("Instância já está conectada — nenhum QR disponível");
        return;
      }
      setQrData(b64);
      setQrTitle(c.instance_name);
      setQrOpen(true);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao obter QR"));
    }
  };

  const openEdit = (c: Channel) => {
    setEditTarget(c);
    setEName(c.name);
    setEPhone(c.phone_number || "");
    setEMode(c.operation_mode);
  };

  const saveEdit = async () => {
    if (!editTarget) return;
    setSaving(true);
    try {
      const body: Record<string, unknown> = {};
      if (eName !== editTarget.name) body.name = eName;
      if (ePhone !== (editTarget.phone_number || "")) body.phone_number = ePhone || null;
      if (eMode !== editTarget.operation_mode) body.operation_mode = eMode;
      if (Object.keys(body).length === 0) {
        setEditTarget(null);
        return;
      }
      await api.patch(`/chatbot/channels/${editTarget.id}`, body);
      toast.success("Canal atualizado");
      setEditTarget(null);
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao salvar"));
    } finally {
      setSaving(false);
    }
  };

  const confirmLogout = async () => {
    if (!logoutTarget?.instance_name) return;
    try {
      await api.post(`/evolution/instances/${logoutTarget.instance_name}/logout`);
      toast.success("Desconectado");
      setLogoutTarget(null);
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao desconectar"));
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget?.instance_name) return;
    try {
      await api.delete(`/evolution/instances/${deleteTarget.instance_name}`);
      toast.success("Instância excluída");
      setDeleteTarget(null);
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao excluir"));
    }
  };

  const updateMode = async (
    channelId: number,
    mode: Channel["operation_mode"],
    flowId?: number | null,
  ) => {
    try {
      await api.put(`/chatbot/channels/${channelId}/mode`, {
        operation_mode: mode,
        active_chatbot_flow_id: mode === "chatbot" ? flowId : null,
        force: true,
      });
      toast.success("Modo atualizado");
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao atualizar modo"));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="mb-1 text-2xl font-semibold tracking-tight">Canais</h1>
          <p className="text-sm text-muted-foreground">
            Instâncias WhatsApp ativas e seu modo operacional.
          </p>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Nova instância Evolution</DialogTitle>
            </DialogHeader>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-2">
                <Label>Nome</Label>
                <Input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="whatsapp_comercial"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label>Finalidade</Label>
                <Select value={newPurpose} onValueChange={setNewPurpose}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="commercial">Comercial</SelectItem>
                    <SelectItem value="ai">IA</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button onClick={createInstance} disabled={creating || !newName.trim()}>
                {creating ? "Criando…" : "Criar"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        <Button onClick={() => setCreateOpen(true)}>Nova instância</Button>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nome</TableHead>
            <TableHead>Telefone</TableHead>
            <TableHead>Instância</TableHead>
            <TableHead>Conectado</TableHead>
            <TableHead>Modo</TableHead>
            <TableHead className="w-16 text-right">Ações</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? (
            <TableRow>
              <TableCell colSpan={6} className="text-center text-sm text-muted-foreground">
                Carregando…
              </TableCell>
            </TableRow>
          ) : channels.length === 0 ? (
            <TableRow>
              <TableCell colSpan={6} className="text-center text-sm text-muted-foreground">
                Nenhum canal. Crie uma instância para começar.
              </TableCell>
            </TableRow>
          ) : (
            channels.map((c) => {
              const badge = statusBadge(c.connection_status);
              return (
                <TableRow key={c.id}>
                  <TableCell>
                    <div>{c.name}</div>
                    {c.profile_name && (
                      <div className="text-[11px] text-muted-foreground">
                        {c.profile_name}
                      </div>
                    )}
                  </TableCell>
                  <TableCell>{formatWaId(c.phone_number || c.owner_jid)}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {c.instance_name || "—"}
                  </TableCell>
                  <TableCell>
                    <span className={cn("inline-flex items-center", badge.cls)}>
                      {badge.label}
                    </span>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Select
                        value={c.operation_mode}
                        onValueChange={(v) =>
                          updateMode(c.id, v as Channel["operation_mode"], c.active_chatbot_flow_id)
                        }
                      >
                        <SelectTrigger className="h-8 w-28">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">none</SelectItem>
                          <SelectItem value="ai">ai</SelectItem>
                          <SelectItem value="chatbot">chatbot</SelectItem>
                        </SelectContent>
                      </Select>
                      {c.operation_mode === "chatbot" && (
                        <Select
                          value={String(c.active_chatbot_flow_id || "")}
                          onValueChange={(v) => updateMode(c.id, "chatbot", Number(v))}
                        >
                          <SelectTrigger className="h-8 w-40">
                            <SelectValue placeholder="Fluxo…" />
                          </SelectTrigger>
                          <SelectContent>
                            {flows
                              .filter((f) => f.is_published)
                              .map((f) => (
                                <SelectItem key={f.id} value={String(f.id)}>
                                  {f.name}
                                </SelectItem>
                              ))}
                          </SelectContent>
                        </Select>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button size="sm" variant="ghost" disabled={!c.instance_name}>
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-48">
                        <DropdownMenuItem onClick={() => showQR(c)}>
                          <QrCode className="mr-2 h-4 w-4" /> Ver QR / Reconectar
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => refreshRow(c)}>
                          <RefreshCw className="mr-2 h-4 w-4" /> Atualizar status
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => openEdit(c)}>
                          <Pencil className="mr-2 h-4 w-4" /> Editar
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onClick={() => setLogoutTarget(c)}
                          className="text-amber-600 focus:text-amber-600 dark:text-amber-400 dark:focus:text-amber-400"
                        >
                          <Power className="mr-2 h-4 w-4" /> Desconectar
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => setDeleteTarget(c)}
                          className="text-destructive focus:text-destructive"
                        >
                          <Trash2 className="mr-2 h-4 w-4" /> Excluir
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>

      {/* QR */}
      <Dialog open={qrOpen} onOpenChange={setQrOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>QR Code — {qrTitle}</DialogTitle>
          </DialogHeader>
          {qrData ? (
            <img src={qrData} alt="QR Code" className="mx-auto" />
          ) : (
            <div className="text-sm text-muted-foreground">Sem QR disponível.</div>
          )}
        </DialogContent>
      </Dialog>

      {/* Edit */}
      <Dialog open={!!editTarget} onOpenChange={(o) => !o && setEditTarget(null)}>
        <DialogContent className="sm:max-w-[440px]">
          <DialogHeader>
            <DialogTitle>Editar canal</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>Nome (local, não afeta Evolution)</Label>
              <Input value={eName} onChange={(e) => setEName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Telefone</Label>
              <Input
                value={ePhone}
                onChange={(e) => setEPhone(e.target.value)}
                placeholder="5515997567886"
              />
            </div>
            <div className="space-y-1">
              <Label>Modo operacional</Label>
              <Select value={eMode} onValueChange={(v) => setEMode(v as Channel["operation_mode"])}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">none</SelectItem>
                  <SelectItem value="ai">ai</SelectItem>
                  <SelectItem
                    value="chatbot"
                    disabled={editTarget?.operation_mode !== "chatbot"}
                  >
                    chatbot (use o seletor de fluxo na tabela)
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditTarget(null)}>
              Cancelar
            </Button>
            <Button onClick={saveEdit} disabled={saving}>
              {saving ? "Salvando…" : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Logout confirm */}
      <AlertDialog open={!!logoutTarget} onOpenChange={(o) => !o && setLogoutTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Desconectar {logoutTarget?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              A instância vai precisar de novo QR Code pra reconectar. Mensagens em
              andamento podem ser perdidas.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={confirmLogout}>Desconectar</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete confirm */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir {deleteTarget?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              Isso apaga a instância do Evolution, remove o canal do banco e cancela
              webhooks configurados. <strong>Irreversível.</strong>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Excluir definitivamente
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
