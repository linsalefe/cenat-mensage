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
  Plus,
  Send,
  FileText,
  Activity,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MetaChannelDialog } from "@/components/canais/meta-channel-dialog";
import { MetaChannelTemplatesDialog } from "@/components/canais/meta-channel-templates-dialog";
import { MetaChannelTestDialog } from "@/components/canais/meta-channel-test-dialog";
import { InstagramChannelDialog } from "@/components/canais/instagram-channel-dialog";
import { InstagramChannelHealthDialog } from "@/components/canais/instagram-channel-health-dialog";
import { BrandInstagram } from "@/components/brand/channel-icon";
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
import { deleteMetaChannel, getMetaChannelHealth } from "@/lib/api-channels-meta";
import { deleteInstagramChannel, updateInstagramChannel } from "@/lib/api-channels-instagram";
import { cn } from "@/lib/utils";
import type {
  Channel,
  ChatbotFlowListItem,
  ConnectionStatus,
  MetaChannelHealth,
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

function TypeBadge({ provider }: { provider: string }) {
  if (provider === "official") {
    return <Badge variant="default">Oficial (Meta)</Badge>;
  }
  if (provider === "instagram") {
    return (
      <Badge className="gap-1 border-transparent bg-fuchsia-500/15 text-fuchsia-600 hover:bg-fuchsia-500/15 dark:text-fuchsia-400">
        <BrandInstagram size={12} /> Instagram
      </Badge>
    );
  }
  return <Badge variant="secondary">QR Code (Evolution)</Badge>;
}

function MetaQualityDot({ health }: { health?: MetaChannelHealth }) {
  if (!health) {
    return (
      <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
        <span className="h-2 w-2 rounded-full bg-zinc-300" />
        carregando…
      </span>
    );
  }
  if (!health.ok) {
    const errStr = typeof health.error === "string" ? health.error : JSON.stringify(health.error);
    return (
      <span
        className="inline-flex items-center gap-2 text-xs text-red-600 dark:text-red-400"
        title={`Erro: ${errStr}`}
      >
        <span className="h-2 w-2 rounded-full bg-red-500" />
        erro
      </span>
    );
  }
  const colorMap: Record<string, string> = {
    GREEN: "bg-emerald-500",
    YELLOW: "bg-amber-500",
    RED: "bg-red-500",
    UNKNOWN: "bg-zinc-400",
  };
  const rating = health.quality_rating || "UNKNOWN";
  const color = colorMap[rating] || "bg-zinc-400";
  const tooltip = `${health.verified_name || "—"} • qualidade ${rating} • verificação ${health.code_verification_status || "?"}`;
  return (
    <span
      className="inline-flex items-center gap-2 text-xs text-muted-foreground"
      title={tooltip}
    >
      <span className={cn("h-2 w-2 rounded-full", color)} />
      {rating.toLowerCase()}
    </span>
  );
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
  const [deleteMetaTarget, setDeleteMetaTarget] = useState<Channel | null>(null);

  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [metaDialogOpen, setMetaDialogOpen] = useState(false);
  const [metaDialogChannel, setMetaDialogChannel] = useState<Channel | null>(null);
  const [metaTestOpen, setMetaTestOpen] = useState(false);
  const [metaTestChannel, setMetaTestChannel] = useState<Channel | null>(null);
  const [metaTemplatesChannel, setMetaTemplatesChannel] = useState<Channel | null>(null);
  const [metaHealth, setMetaHealth] = useState<Record<number, MetaChannelHealth>>({});

  const [igDialogOpen, setIgDialogOpen] = useState(false);
  const [igDialogChannel, setIgDialogChannel] = useState<Channel | null>(null);
  const [igHealthChannel, setIgHealthChannel] = useState<Channel | null>(null);
  const [deleteIgTarget, setDeleteIgTarget] = useState<Channel | null>(null);

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

  useEffect(() => {
    const metaCh = channels.filter((c) => c.provider === "official");
    if (metaCh.length === 0) {
      setMetaHealth({});
      return;
    }
    let cancelled = false;
    Promise.all(
      metaCh.map((c) =>
        getMetaChannelHealth(c.id)
          .then((h) => [c.id, h] as const)
          .catch(() => [c.id, { channel_id: c.id, ok: false, error: "request failed" }] as const),
      ),
    ).then((entries) => {
      if (cancelled) return;
      const next: Record<number, MetaChannelHealth> = {};
      for (const [id, h] of entries) next[id] = h;
      setMetaHealth(next);
    });
    return () => {
      cancelled = true;
    };
  }, [channels]);

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

  const openCreateMeta = () => {
    setMetaDialogChannel(null);
    setMetaDialogOpen(true);
    setAddMenuOpen(false);
  };

  const openEditMeta = (c: Channel) => {
    setMetaDialogChannel(c);
    setMetaDialogOpen(true);
  };

  const openTestMeta = (c: Channel) => {
    setMetaTestChannel(c);
    setMetaTestOpen(true);
  };

  const confirmDeleteMeta = async () => {
    if (!deleteMetaTarget) return;
    try {
      await deleteMetaChannel(deleteMetaTarget.id);
      toast.success("Canal Meta excluído");
      setDeleteMetaTarget(null);
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao excluir canal Meta"));
    }
  };

  const openCreateIg = () => {
    setIgDialogChannel(null);
    setIgDialogOpen(true);
    setAddMenuOpen(false);
  };

  const openEditIg = (c: Channel) => {
    setIgDialogChannel(c);
    setIgDialogOpen(true);
  };

  const toggleIgActive = async (c: Channel) => {
    try {
      await updateInstagramChannel(c.id, { is_active: !c.is_active });
      toast.success(c.is_active ? "Canal desativado" : "Canal ativado");
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao atualizar canal"));
    }
  };

  const confirmDeleteIg = async () => {
    if (!deleteIgTarget) return;
    try {
      await deleteInstagramChannel(deleteIgTarget.id);
      toast.success("Canal Instagram excluído");
      setDeleteIgTarget(null);
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao excluir canal Instagram"));
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
        <DropdownMenu open={addMenuOpen} onOpenChange={setAddMenuOpen}>
          <DropdownMenuTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" /> Adicionar canal
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64">
            <DropdownMenuItem
              onClick={() => {
                setAddMenuOpen(false);
                setCreateOpen(true);
              }}
            >
              <QrCode className="mr-2 h-4 w-4" /> WhatsApp QR Code (Evolution)
            </DropdownMenuItem>
            <DropdownMenuItem onClick={openCreateMeta}>
              <Send className="mr-2 h-4 w-4" /> WhatsApp Oficial (Meta)
            </DropdownMenuItem>
            <DropdownMenuItem onClick={openCreateIg}>
              <BrandInstagram size={16} className="mr-2" /> Instagram (Direct)
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nome</TableHead>
            <TableHead>Tipo</TableHead>
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
              <TableCell colSpan={7} className="text-center text-sm text-muted-foreground">
                Carregando…
              </TableCell>
            </TableRow>
          ) : channels.length === 0 ? (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-sm text-muted-foreground">
                Nenhum canal. Adicione um para começar.
              </TableCell>
            </TableRow>
          ) : (
            channels.map((c) => {
              const isMeta = c.provider === "official";
              const isInstagram = c.provider === "instagram";
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
                  <TableCell>
                    <TypeBadge provider={c.provider} />
                  </TableCell>
                  <TableCell>{formatWaId(c.phone_number || c.owner_jid)}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {c.instance_name || "—"}
                  </TableCell>
                  <TableCell>
                    {isMeta ? (
                      <MetaQualityDot health={metaHealth[c.id]} />
                    ) : isInstagram ? (
                      <span
                        className={cn(
                          "inline-flex items-center gap-2 text-xs",
                          c.is_active
                            ? "text-emerald-600 dark:text-emerald-400"
                            : "text-zinc-500",
                        )}
                      >
                        <span
                          className={cn(
                            "h-2 w-2 rounded-full",
                            c.is_active ? "bg-emerald-500" : "bg-zinc-400",
                          )}
                        />
                        {c.is_active ? "ativo" : "inativo"}
                      </span>
                    ) : (
                      <span className={cn("inline-flex items-center", badge.cls)}>
                        {badge.label}
                      </span>
                    )}
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
                        <Button size="sm" variant="ghost">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-48">
                        {isMeta ? (
                          <>
                            <DropdownMenuItem onClick={() => openTestMeta(c)}>
                              <Send className="mr-2 h-4 w-4" /> Testar envio
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => setMetaTemplatesChannel(c)}>
                              <FileText className="mr-2 h-4 w-4" /> Templates
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => openEditMeta(c)}>
                              <Pencil className="mr-2 h-4 w-4" /> Editar
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => setDeleteMetaTarget(c)}
                              className="text-destructive focus:text-destructive"
                            >
                              <Trash2 className="mr-2 h-4 w-4" /> Excluir
                            </DropdownMenuItem>
                          </>
                        ) : isInstagram ? (
                          <>
                            <DropdownMenuItem onClick={() => setIgHealthChannel(c)}>
                              <Activity className="mr-2 h-4 w-4" /> Health (@username)
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => openEditIg(c)}>
                              <Pencil className="mr-2 h-4 w-4" /> Editar
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => toggleIgActive(c)}>
                              <Power className="mr-2 h-4 w-4" />
                              {c.is_active ? "Desativar" : "Ativar"}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => setDeleteIgTarget(c)}
                              className="text-destructive focus:text-destructive"
                            >
                              <Trash2 className="mr-2 h-4 w-4" /> Excluir
                            </DropdownMenuItem>
                          </>
                        ) : (
                          <>
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
                          </>
                        )}
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

      {/* Delete Meta confirm */}
      <AlertDialog
        open={!!deleteMetaTarget}
        onOpenChange={(o) => !o && setDeleteMetaTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir canal Meta {deleteMetaTarget?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              Remove o registro do canal no banco. O número segue ativo no painel da Meta;
              só pode ser usado novamente após recadastro. <strong>Irreversível aqui.</strong>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDeleteMeta}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Excluir definitivamente
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <MetaChannelDialog
        open={metaDialogOpen}
        onOpenChange={setMetaDialogOpen}
        channel={metaDialogChannel}
        onSuccess={load}
      />

      <MetaChannelTestDialog
        open={metaTestOpen}
        onOpenChange={setMetaTestOpen}
        channel={metaTestChannel}
      />

      <MetaChannelTemplatesDialog
        open={!!metaTemplatesChannel}
        onOpenChange={(o) => !o && setMetaTemplatesChannel(null)}
        channelId={metaTemplatesChannel?.id ?? null}
        channelName={metaTemplatesChannel?.name ?? ""}
      />

      <InstagramChannelDialog
        open={igDialogOpen}
        onOpenChange={setIgDialogOpen}
        channel={igDialogChannel}
        onSuccess={load}
      />

      <InstagramChannelHealthDialog
        open={!!igHealthChannel}
        onOpenChange={(o) => !o && setIgHealthChannel(null)}
        channel={igHealthChannel}
      />

      {/* Delete Instagram confirm */}
      <AlertDialog open={!!deleteIgTarget} onOpenChange={(o) => !o && setDeleteIgTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir canal Instagram {deleteIgTarget?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              Remove o registro do canal no banco. A conta segue no Instagram; só pode ser
              usada novamente após recadastro. <strong>Irreversível aqui.</strong>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDeleteIg}
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
