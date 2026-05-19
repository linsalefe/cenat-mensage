"use client";

import { useEffect, useState } from "react";
import axios from "axios";
import { Megaphone } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
import { api } from "@/lib/api";
import { campaignsApi } from "@/lib/api-campaigns";
import { contactListsApi } from "@/lib/api-contact-lists";
import type { Channel, ContactList } from "@/types/api";

interface Props {
  flowId: number;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onStarted?: (runId: number) => void;
}

function errMsg(err: unknown, fallback = "Erro inesperado") {
  if (axios.isAxiosError(err) && err.response?.data?.detail) {
    const d = err.response.data.detail;
    return typeof d === "string" ? d : JSON.stringify(d);
  }
  return fallback;
}

export function StartCampaignDialog({ flowId, open, onOpenChange, onStarted }: Props) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [lists, setLists] = useState<ContactList[]>([]);
  const [channelId, setChannelId] = useState<string>("");
  const [listId, setListId] = useState<string>("");
  const [interval, setInterval] = useState<number>(2);
  const [dailyLimit, setDailyLimit] = useState<string>("");
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (!open) return;
    Promise.all([api.get<Channel[]>("/meta/channels"), contactListsApi.list()])
      .then(([chRes, ls]) => {
        setChannels(chRes.data || []);
        setLists(ls);
      })
      .catch(() => undefined);
  }, [open]);

  const selectedList = lists.find((l) => String(l.id) === listId) || null;

  async function handleStart() {
    if (!channelId) {
      toast.error("Selecione um canal");
      return;
    }
    if (!listId) {
      toast.error("Selecione uma lista");
      return;
    }
    setStarting(true);
    try {
      const run = await campaignsApi.start({
        flow_id: flowId,
        channel_id: Number(channelId),
        list_id: Number(listId),
        batch_interval_seconds: interval,
        daily_limit: dailyLimit ? Number(dailyLimit) : null,
      });
      toast.success(`Campanha iniciada (run #${run.id})`);
      onStarted?.(run.id);
      onOpenChange(false);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao iniciar campanha"));
    } finally {
      setStarting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Megaphone className="h-4 w-4" /> Disparar campanha
          </DialogTitle>
          <DialogDescription>
            Cria uma sessão por contato da lista. Mensagens disparam respeitando o intervalo.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Canal Meta</Label>
            <Select value={channelId} onValueChange={setChannelId}>
              <SelectTrigger>
                <SelectValue placeholder="Selecione um canal" />
              </SelectTrigger>
              <SelectContent>
                {channels.length === 0 ? (
                  <SelectItem value="__empty__" disabled>
                    Nenhum canal Meta — cadastre em /canais
                  </SelectItem>
                ) : (
                  channels.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.name}
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Lista</Label>
            <Select value={listId} onValueChange={setListId}>
              <SelectTrigger>
                <SelectValue placeholder="Selecione uma lista" />
              </SelectTrigger>
              <SelectContent>
                {lists.length === 0 ? (
                  <SelectItem value="__empty__" disabled>
                    Nenhuma lista — crie em /listas
                  </SelectItem>
                ) : (
                  lists.map((l) => (
                    <SelectItem key={l.id} value={String(l.id)}>
                      {l.name} ({l.member_count} contatos)
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Intervalo entre envios (segundos)</Label>
            <Input
              type="number"
              min={1}
              value={interval}
              onChange={(e) => setInterval(Number(e.target.value) || 2)}
            />
          </div>

          <div className="space-y-2">
            <Label>Limite diário (opcional)</Label>
            <Input
              type="number"
              min={1}
              value={dailyLimit}
              onChange={(e) => setDailyLimit(e.target.value)}
              placeholder="Ex: 1000"
            />
          </div>

          {selectedList && (
            <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
              <strong>{selectedList.member_count}</strong> contatos receberão a mensagem inicial do
              fluxo (opt-out filtrado automaticamente).
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={starting}>
            Cancelar
          </Button>
          <Button onClick={handleStart} disabled={starting}>
            {starting ? "Iniciando…" : "Iniciar campanha"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
