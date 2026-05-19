"use client";

import { useEffect, useState } from "react";
import axios from "axios";
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
import { Textarea } from "@/components/ui/textarea";
import { sendMetaTemplate, sendMetaText } from "@/lib/api-channels-meta";
import type { Channel } from "@/types/api";

type Mode = "template" | "text";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  channel: Channel | null;
}

function errMsg(err: unknown, fallback = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fallback;
}

export function MetaChannelTestDialog({ open, onOpenChange, channel }: Props) {
  const [mode, setMode] = useState<Mode>("template");
  const [to, setTo] = useState("");
  const [text, setText] = useState("");
  const [templateName, setTemplateName] = useState("hello_world");
  const [languageCode, setLanguageCode] = useState("en_US");
  const [sending, setSending] = useState(false);
  const [lastResult, setLastResult] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setMode("template");
    setTo("");
    setText("");
    setTemplateName("hello_world");
    setLanguageCode("en_US");
    setLastResult(null);
  }, [open]);

  async function handleSend() {
    if (!channel) return;
    if (!to.trim()) {
      toast.error("Informe o número de destino");
      return;
    }
    if (mode === "text" && !text.trim()) {
      toast.error("Informe o texto");
      return;
    }
    if (mode === "template" && !templateName.trim()) {
      toast.error("Informe o nome do template");
      return;
    }

    setSending(true);
    setLastResult(null);
    try {
      if (mode === "text") {
        const r = await sendMetaText(channel.id, { to: to.trim(), text: text.trim() });
        setLastResult(`OK — wa_message_id: ${r.wa_message_id}`);
        toast.success("Mensagem enviada");
      } else {
        const r = await sendMetaTemplate(channel.id, {
          to: to.trim(),
          template_name: templateName.trim(),
          language_code: languageCode.trim() || "en_US",
        });
        setLastResult(`OK — wa_message_id: ${r.wa_message_id}`);
        toast.success("Template enviado");
      }
    } catch (err) {
      const msg = errMsg(err, "Falha ao enviar");
      setLastResult(`Erro: ${msg}`);
      toast.error(msg);
    } finally {
      setSending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Testar envio — {channel?.name}</DialogTitle>
        </DialogHeader>

        <div className="mt-2 space-y-4">
          <div className="space-y-1">
            <Label>Tipo</Label>
            <Select value={mode} onValueChange={(v) => v && setMode(v as Mode)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="template">Template (fora da janela 24h)</SelectItem>
                <SelectItem value="text">Texto livre (dentro da janela 24h)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label htmlFor="test-to">Destinatário (com DDI)</Label>
            <Input
              id="test-to"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder="5583988046720"
            />
          </div>

          {mode === "template" ? (
            <>
              <div className="space-y-1">
                <Label htmlFor="test-template">Nome do template</Label>
                <Input
                  id="test-template"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  placeholder="hello_world"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="test-lang">Código do idioma</Label>
                <Input
                  id="test-lang"
                  value={languageCode}
                  onChange={(e) => setLanguageCode(e.target.value)}
                  placeholder="en_US ou pt_BR"
                />
              </div>
            </>
          ) : (
            <div className="space-y-1">
              <Label htmlFor="test-text">Texto</Label>
              <Textarea
                id="test-text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={3}
                placeholder="Mensagem de teste"
              />
            </div>
          )}

          {lastResult && (
            <div className="whitespace-pre-wrap rounded bg-muted p-2 font-mono text-xs">
              {lastResult}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={sending}>
            Fechar
          </Button>
          <Button onClick={handleSend} disabled={sending}>
            {sending ? "Enviando..." : "Enviar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
