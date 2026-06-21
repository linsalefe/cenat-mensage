"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, Plus, Save, Trash2 } from "lucide-react";
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
import { type ColumnInput, updateColumns } from "@/lib/api-crm";
import type { Pipeline, PipelineColumn } from "@/types/api";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  pipeline: Pipeline | null;
  onSaved: (p: Pipeline) => void;
}

interface Row {
  key?: string;
  label: string;
  color: string;
}

const PRESET = ["#10b981", "#22c55e", "#06b6d4", "#0ea5e9", "#8b5cf6", "#a855f7", "#f59e0b", "#ef4444", "#64748b"];

export function ColumnEditorDialog({ open, onOpenChange, pipeline, onSaved }: Props) {
  const [rows, setRows] = useState<Row[]>([]);
  const [newLabel, setNewLabel] = useState("");
  const [newColor, setNewColor] = useState("#10b981");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open && pipeline) {
      const cols = [...pipeline.columns].sort((a, b) => a.order - b.order);
      setRows(cols.map((c: PipelineColumn) => ({ key: c.key, label: c.label, color: c.color })));
      setNewLabel("");
      setNewColor("#10b981");
    }
  }, [open, pipeline]);

  const setLabel = (i: number, label: string) =>
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, label } : row)));
  const setColor = (i: number, color: string) =>
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, color } : row)));
  const remove = (i: number) => setRows((r) => r.filter((_, idx) => idx !== i));
  const move = (i: number, dir: -1 | 1) =>
    setRows((r) => {
      const j = i + dir;
      if (j < 0 || j >= r.length) return r;
      const copy = [...r];
      [copy[i], copy[j]] = [copy[j], copy[i]];
      return copy;
    });
  const add = () => {
    if (!newLabel.trim()) return;
    setRows((r) => [...r, { label: newLabel.trim(), color: newColor }]);
    setNewLabel("");
    setNewColor("#10b981");
  };

  const save = async () => {
    if (!pipeline) return;
    if (rows.length === 0) {
      toast.error("O funil precisa de pelo menos uma etapa");
      return;
    }
    if (rows.some((r) => !r.label.trim())) {
      toast.error("Toda etapa precisa de um nome");
      return;
    }
    setSaving(true);
    try {
      const payload: ColumnInput[] = rows.map((r, idx) => ({
        key: r.key,
        label: r.label.trim(),
        color: r.color,
        order: idx,
      }));
      const updated = await updateColumns(pipeline.id, payload);
      toast.success("Etapas atualizadas");
      onSaved(updated);
      onOpenChange(false);
    } catch {
      toast.error("Falha ao salvar etapas");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] max-w-lg flex-col">
        <DialogHeader>
          <DialogTitle>Editar etapas — {pipeline?.name}</DialogTitle>
        </DialogHeader>

        <div className="flex-1 space-y-2 overflow-y-auto py-2">
          {rows.map((row, i) => (
            <div key={i} className="flex items-center gap-2 rounded-lg border border-border bg-muted/40 p-2">
              <div className="flex flex-col">
                <button
                  onClick={() => move(i, -1)}
                  disabled={i === 0}
                  className="text-muted-foreground hover:text-foreground disabled:opacity-30"
                  aria-label="Subir"
                >
                  <ChevronUp className="h-4 w-4" />
                </button>
                <button
                  onClick={() => move(i, 1)}
                  disabled={i === rows.length - 1}
                  className="text-muted-foreground hover:text-foreground disabled:opacity-30"
                  aria-label="Descer"
                >
                  <ChevronDown className="h-4 w-4" />
                </button>
              </div>
              <div className="relative h-7 w-7 shrink-0">
                <input
                  type="color"
                  value={row.color}
                  onChange={(e) => setColor(i, e.target.value)}
                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                  aria-label="Cor"
                />
                <div
                  className="h-7 w-7 rounded-lg border-2 border-background shadow-sm"
                  style={{ backgroundColor: row.color }}
                />
              </div>
              <Input
                value={row.label}
                onChange={(e) => setLabel(i, e.target.value)}
                className="h-8 flex-1"
              />
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
                onClick={() => remove(i)}
                aria-label="Remover etapa"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
          {rows.length === 0 && (
            <p className="py-4 text-center text-sm text-muted-foreground">
              Sem etapas — adicione ao menos uma abaixo.
            </p>
          )}
        </div>

        <div className="border-t border-border pt-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Nova etapa
          </p>
          <div className="flex items-center gap-2">
            <div className="relative h-8 w-8 shrink-0">
              <input
                type="color"
                value={newColor}
                onChange={(e) => setNewColor(e.target.value)}
                className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                aria-label="Cor da nova etapa"
              />
              <div
                className="h-8 w-8 rounded-lg border-2 border-background shadow-sm"
                style={{ backgroundColor: newColor }}
              />
            </div>
            <Input
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && add()}
              placeholder="Nome da etapa…"
              className="h-9 flex-1"
            />
            <Button size="sm" onClick={add} disabled={!newLabel.trim()}>
              <Plus className="mr-1 h-3.5 w-3.5" /> Adicionar
            </Button>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {PRESET.map((c) => (
              <button
                key={c}
                onClick={() => setNewColor(c)}
                className="h-5 w-5 rounded-md border-2"
                style={{ backgroundColor: c, borderColor: newColor === c ? "hsl(var(--foreground))" : "transparent" }}
                aria-label={`Cor ${c}`}
              />
            ))}
          </div>
        </div>

        <DialogFooter className="pt-2">
          <p className="flex-1 text-[11px] text-muted-foreground">
            Renomear/recolorir mantém os contatos; remover etapa move os contatos pra 1ª.
          </p>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancelar
          </Button>
          <Button onClick={save} disabled={saving}>
            <Save className="mr-1.5 h-3.5 w-3.5" /> {saving ? "Salvando…" : "Salvar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
