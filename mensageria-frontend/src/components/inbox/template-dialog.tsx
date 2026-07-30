"use client";

import { useEffect, useMemo, useState } from "react";
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
import { inboxApi } from "@/lib/api-inbox";
import { templatesApi } from "@/lib/api-templates";
import type { MetaTemplate } from "@/types/api";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  channelId: number;
  to: string;
  onSent: () => void;
}

function bodyText(t: MetaTemplate): string {
  const body = (t.components ?? []).find(
    (c) => String((c as { type?: string }).type).toUpperCase() === "BODY",
  ) as { text?: string } | undefined;
  return body?.text ?? "";
}

/** Conta os placeholders {{1}}, {{2}}… do corpo do template. */
function placeholderCount(t: MetaTemplate): number {
  const matches = bodyText(t).match(/\{\{\s*(\d+)\s*\}\}/g);
  if (!matches) return 0;
  const nums = matches.map((m) => Number(m.replace(/\D/g, "")));
  return Math.max(...nums);
}

export function TemplateDialog({ open, onOpenChange, channelId, to, onSent }: Props) {
  const [templates, setTemplates] = useState<MetaTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string>("");
  const [params, setParams] = useState<string[]>([]);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    templatesApi
      .list(channelId, "APPROVED")
      .then(setTemplates)
      .catch(() => toast.error("Falha ao carregar os templates"))
      .finally(() => setLoading(false));
  }, [open, channelId]);

  const selected = useMemo(
    () => templates.find((t) => String(t.id) === selectedId) ?? null,
    [templates, selectedId],
  );

  const count = selected ? placeholderCount(selected) : 0;

  useEffect(() => {
    setParams(Array.from({ length: count }, () => ""));
  }, [count, selectedId]);

  const preview = useMemo(() => {
    if (!selected) return "";
    return bodyText(selected).replace(/\{\{\s*(\d+)\s*\}\}/g, (_, n) => {
      const v = params[Number(n) - 1];
      return v?.trim() ? v : `{{${n}}}`;
    });
  }, [selected, params]);

  const ready = !!selected && params.every((p) => p.trim() !== "");

  const send = async () => {
    if (!selected || !ready) return;
    setSending(true);
    try {
      const components =
        count > 0
          ? [
              {
                type: "body",
                parameters: params.map((text) => ({ type: "text", text })),
              },
            ]
          : undefined;
      await inboxApi.sendTemplate(channelId, {
        to,
        template_name: selected.name,
        language_code: selected.language,
        components,
      });
      toast.success("Template enviado");
      onOpenChange(false);
      setSelectedId("");
      onSent();
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Falha ao enviar o template");
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="wa-theme sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Enviar template</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Template aprovado</Label>
            <Select value={selectedId} onValueChange={setSelectedId} disabled={loading}>
              <SelectTrigger>
                <SelectValue
                  placeholder={loading ? "Carregando…" : "Escolha um template"}
                />
              </SelectTrigger>
              <SelectContent className="wa-theme">
                {templates.map((t) => (
                  <SelectItem key={t.id} value={String(t.id)}>
                    {t.name} · {t.language}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!loading && templates.length === 0 && (
              <p className="text-[11px] text-muted-foreground">
                Nenhum template aprovado neste canal. Sincronize em Canais.
              </p>
            )}
          </div>

          {count > 0 && (
            <div className="space-y-2">
              <Label className="text-xs">Variáveis do corpo</Label>
              {params.map((v, i) => (
                <Input
                  key={i}
                  value={v}
                  onChange={(e) => {
                    const next = [...params];
                    next[i] = e.target.value;
                    setParams(next);
                  }}
                  placeholder={`Valor de {{${i + 1}}}`}
                  className="text-xs"
                />
              ))}
            </div>
          )}

          {selected && (
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Prévia</Label>
              <div className="whitespace-pre-wrap rounded-lg bg-muted p-3 text-xs">
                {preview}
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button onClick={send} disabled={!ready || sending}>
            {sending ? "Enviando…" : "Enviar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
