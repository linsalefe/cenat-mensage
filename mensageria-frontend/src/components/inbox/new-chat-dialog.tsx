"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
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
import { inboxApi, normalizePhone } from "@/lib/api-inbox";
import type { Channel, Contact } from "@/types/api";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  channels: Channel[];
  /** `withTemplate` pede que a página abra o diálogo de template em seguida. */
  onCreated: (contact: Contact, withTemplate: boolean) => void;
}

export function NewChatDialog({ open, onOpenChange, channels, onCreated }: Props) {
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [channelId, setChannelId] = useState<string>("");
  const [saving, setSaving] = useState(false);

  // Instagram não permite iniciar conversa a partir de um id digitado.
  const usable = channels.filter((c) => c.provider !== "instagram");
  const chosen = usable.find((c) => String(c.id) === channelId) ?? null;
  const normalized = normalizePhone(phone);
  const valid = normalized.length >= 12 && normalized.length <= 13 && !!chosen;

  const submit = async (withTemplate: boolean) => {
    if (!valid || !chosen) return;
    setSaving(true);
    try {
      const contact = await inboxApi.createContact(
        normalized,
        name.trim() || undefined,
        chosen.id,
      );
      onCreated(contact, withTemplate);
      onOpenChange(false);
      setPhone("");
      setName("");
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Falha ao criar a conversa");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="wa-theme sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Nova conversa</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Canal</Label>
            <Select value={channelId} onValueChange={setChannelId}>
              <SelectTrigger>
                <SelectValue placeholder="Escolha o canal" />
              </SelectTrigger>
              <SelectContent className="wa-theme">
                {usable.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Telefone</Label>
            <Input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="(15) 99756-7886"
              inputMode="tel"
            />
            {phone.trim() !== "" && (
              <p className="text-[11px] text-muted-foreground">
                {valid || !chosen
                  ? `Será salvo como ${normalized}`
                  : "Número inválido — informe DDD + número."}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Nome (opcional)</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Como identificar este contato"
            />
          </div>

          {chosen?.provider === "official" && (
            <p className="rounded-md bg-muted p-2 text-[11px] text-muted-foreground">
              Este contato nunca escreveu, então a janela de 24 horas está
              fechada: o WhatsApp só entrega por template. Uma mensagem de texto
              comum vai falhar.
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            variant={chosen?.provider === "official" ? "outline" : "default"}
            onClick={() => submit(false)}
            disabled={!valid || saving}
          >
            {saving ? "Criando…" : "Só abrir conversa"}
          </Button>
          {chosen?.provider === "official" && (
            <Button onClick={() => submit(true)} disabled={!valid || saving}>
              {saving ? "Criando…" : "Abrir e enviar template"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
