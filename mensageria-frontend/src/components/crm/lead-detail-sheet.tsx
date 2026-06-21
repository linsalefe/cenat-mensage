"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { MessageCircle, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ChannelIcon } from "@/components/brand/channel-icon";
import { avatarColor, cardName, stripIg } from "@/components/crm/kanban-card";
import { updateCard } from "@/lib/api-crm";
import { cn } from "@/lib/utils";
import type { KanbanCard, PipelineColumn } from "@/types/api";

interface Props {
  card: KanbanCard | null;
  columns: PipelineColumn[];
  onClose: () => void;
  onChanged: (card: KanbanCard) => void;
}

export function LeadDetailSheet({ card, columns, onClose, onChanged }: Props) {
  const router = useRouter();
  const [notes, setNotes] = useState("");
  const [dealValue, setDealValue] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (card) {
      setNotes(card.notes || "");
      setDealValue(card.deal_value != null ? String(card.deal_value) : "");
    }
  }, [card]);

  if (!card) return null;

  const name = cardName(card);

  const changeStage = async (status: string) => {
    try {
      const updated = await updateCard(card.id, { lead_status: status });
      onChanged(updated);
    } catch {
      toast.error("Falha ao mudar a etapa");
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      const updated = await updateCard(card.id, {
        notes,
        deal_value: dealValue ? Number(dealValue) : 0,
      });
      onChanged(updated);
      toast.success("Lead atualizado");
    } catch {
      toast.error("Falha ao salvar");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />
      <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-card shadow-xl">
        <div className="flex items-center justify-between border-b border-border p-4">
          <div className="flex min-w-0 items-center gap-3">
            <div
              className={cn(
                "flex h-10 w-10 items-center justify-center rounded-full text-sm font-semibold text-white",
                avatarColor(name),
              )}
            >
              {name[0]?.toUpperCase() || "?"}
            </div>
            <div className="min-w-0">
              <div className="truncate font-semibold">{name}</div>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <ChannelIcon provider={card.provider} size={14} />
                <span className="truncate">{stripIg(card.wa_id)}</span>
              </div>
            </div>
          </div>
          <Button size="icon" variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          <div className="space-y-1">
            <Label>Etapa</Label>
            <Select value={card.lead_status || ""} onValueChange={changeStage}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {columns.map((c) => (
                  <SelectItem key={c.key} value={c.key}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label htmlFor="lead-deal">Valor do negócio (R$)</Label>
            <Input
              id="lead-deal"
              type="number"
              value={dealValue}
              onChange={(e) => setDealValue(e.target.value)}
              placeholder="0"
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="lead-notes">Observações</Label>
            <Textarea
              id="lead-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={5}
              placeholder="Anotações sobre o lead…"
            />
          </div>

          <Button onClick={save} disabled={saving} className="w-full">
            {saving ? "Salvando…" : "Salvar"}
          </Button>
        </div>

        <div className="border-t border-border p-4">
          <Button
            variant="outline"
            className="w-full"
            onClick={() => router.push(`/conversations?contact=${card.id}`)}
          >
            <MessageCircle className="mr-2 h-4 w-4" /> Abrir conversa
          </Button>
        </div>
      </div>
    </>
  );
}
