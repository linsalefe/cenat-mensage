"use client";

import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
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
import type { Channel, ChatbotFlowListItem } from "@/types/api";

function errMsg(err: unknown, fallback = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fallback;
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
      // show QR
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

  const showQR = async (instanceName: string) => {
    try {
      const res = await api.get(`/evolution/instances/${instanceName}/qrcode`);
      setQrData(res.data.base64 || res.data.qrcode?.base64 || null);
      setQrTitle(instanceName);
      setQrOpen(true);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao obter QR"));
    }
  };

  const refreshStatus = async (instanceName: string) => {
    try {
      const res = await api.get(`/evolution/instances/${instanceName}/status`);
      toast.success(`${instanceName}: ${res.data.state}`);
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao consultar status"));
    }
  };

  const logoutInstance = async (instanceName: string) => {
    if (!confirm(`Desconectar WhatsApp de ${instanceName}?`)) return;
    try {
      await api.post(`/evolution/instances/${instanceName}/logout`);
      toast.success("Desconectado");
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao desconectar"));
    }
  };

  const deleteInstance = async (instanceName: string) => {
    if (!confirm(`Deletar instância ${instanceName}? Esta ação é irreversível.`)) return;
    try {
      await api.delete(`/evolution/instances/${instanceName}`);
      toast.success("Instância deletada");
      await load();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao deletar"));
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
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Canais</h1>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button>Nova instância</Button>
          </DialogTrigger>
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
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nome</TableHead>
            <TableHead>Telefone</TableHead>
            <TableHead>Instância</TableHead>
            <TableHead>Conectado</TableHead>
            <TableHead>Modo</TableHead>
            <TableHead className="text-right">Ações</TableHead>
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
            channels.map((c) => (
              <TableRow key={c.id}>
                <TableCell>{c.name}</TableCell>
                <TableCell>{c.phone_number || "—"}</TableCell>
                <TableCell className="font-mono text-xs">{c.instance_name || "—"}</TableCell>
                <TableCell>
                  {c.is_connected ? (
                    <Badge variant="default">conectado</Badge>
                  ) : (
                    <Badge variant="secondary">offline</Badge>
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
                  <div className="flex justify-end gap-1">
                    {c.instance_name && (
                      <>
                        <Button size="sm" variant="outline" onClick={() => showQR(c.instance_name!)}>
                          QR
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => refreshStatus(c.instance_name!)}>
                          Status
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => logoutInstance(c.instance_name!)}>
                          Logout
                        </Button>
                        <Button size="sm" variant="destructive" onClick={() => deleteInstance(c.instance_name!)}>
                          Deletar
                        </Button>
                      </>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

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
    </div>
  );
}
