"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { DragDropContext, DropResult } from "@hello-pangea/dnd";
import { MoreVertical, Pencil, Plus, RefreshCw, Search, Settings2, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { BrandInstagram, BrandWhatsApp } from "@/components/brand/channel-icon";
import { KanbanColumn } from "@/components/crm/kanban-column";
import { ColumnEditorDialog } from "@/components/crm/column-editor-dialog";
import { LeadDetailSheet } from "@/components/crm/lead-detail-sheet";
import {
  createPipeline,
  deletePipeline,
  listKanbanCards,
  listPipelines,
  moveCard,
  updatePipeline,
} from "@/lib/api-crm";
import { cn } from "@/lib/utils";
import type { KanbanCard, Pipeline } from "@/types/api";

type ChannelTab = "all" | "whatsapp" | "instagram";

const kindOf = (provider?: string | null): Exclude<ChannelTab, "all"> =>
  provider === "instagram" ? "instagram" : "whatsapp";

export default function CrmPage() {
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [cards, setCards] = useState<KanbanCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<ChannelTab>("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<KanbanCard | null>(null);

  const [editorOpen, setEditorOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [funnelName, setFunnelName] = useState("");
  const [savingFunnel, setSavingFunnel] = useState(false);

  const active = pipelines.find((p) => p.id === activeId) || null;
  const columns = useMemo(
    () => [...(active?.columns || [])].sort((a, b) => a.order - b.order),
    [active],
  );

  useEffect(() => {
    (async () => {
      try {
        const ps = await listPipelines();
        setPipelines(ps);
        const def = ps.find((p) => p.is_default) || ps[0];
        setActiveId(def?.id ?? null);
      } catch {
        toast.error("Falha ao carregar funis");
        setLoading(false);
      }
    })();
  }, []);

  const loadCards = useCallback(async (pid: number) => {
    setLoading(true);
    try {
      setCards(await listKanbanCards(pid));
    } catch {
      toast.error("Falha ao carregar contatos");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeId != null) loadCards(activeId);
  }, [activeId, loadCards]);

  const baseFiltered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return cards.filter((c) => {
      if (tab !== "all" && kindOf(c.provider) !== tab) return false;
      if (q) {
        const hay = `${c.name || ""} ${c.wa_id}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [cards, tab, search]);

  const counts = useMemo(() => {
    const q = search.trim().toLowerCase();
    const searched = cards.filter(
      (c) => !q || `${c.name || ""} ${c.wa_id}`.toLowerCase().includes(q),
    );
    let wpp = 0;
    let ig = 0;
    searched.forEach((c) => (kindOf(c.provider) === "instagram" ? ig++ : wpp++));
    return { all: searched.length, whatsapp: wpp, instagram: ig };
  }, [cards, search]);

  const cardsByStatus = (key: string) => baseFiltered.filter((c) => (c.lead_status || "novo") === key);

  const onDragEnd = (result: DropResult) => {
    const { draggableId, destination, source } = result;
    if (!destination || destination.droppableId === source.droppableId) return;
    const id = Number(draggableId);
    const newStatus = destination.droppableId;
    const prev = cards;
    setCards((cs) => cs.map((c) => (c.id === id ? { ...c, lead_status: newStatus } : c)));
    moveCard(id, newStatus).catch(() => {
      toast.error("Falha ao mover — desfazendo");
      setCards(prev);
    });
  };

  const applyChanged = (updated: KanbanCard) => {
    setCards((cs) => cs.map((c) => (c.id === updated.id ? updated : c)));
    setSelected(updated);
  };

  const applyPipeline = (p: Pipeline) =>
    setPipelines((ps) => ps.map((x) => (x.id === p.id ? p : x)));

  const handleCreate = async () => {
    if (!funnelName.trim()) return;
    setSavingFunnel(true);
    try {
      const p = await createPipeline(funnelName.trim());
      setPipelines((ps) => [...ps, p]);
      setActiveId(p.id);
      setCreateOpen(false);
      setFunnelName("");
      toast.success("Funil criado");
    } catch {
      toast.error("Falha ao criar funil");
    } finally {
      setSavingFunnel(false);
    }
  };

  const handleRename = async () => {
    if (!active || !funnelName.trim()) return;
    setSavingFunnel(true);
    try {
      const p = await updatePipeline(active.id, { name: funnelName.trim() });
      applyPipeline(p);
      setRenameOpen(false);
      toast.success("Funil renomeado");
    } catch {
      toast.error("Falha ao renomear");
    } finally {
      setSavingFunnel(false);
    }
  };

  const handleDelete = async () => {
    if (!active || active.is_default) return;
    try {
      await deletePipeline(active.id);
      const remaining = pipelines.filter((p) => p.id !== active.id);
      setPipelines(remaining);
      const def = remaining.find((p) => p.is_default) || remaining[0];
      setActiveId(def?.id ?? null);
      setDeleteOpen(false);
      toast.success("Funil excluído — contatos voltaram ao funil padrão");
    } catch {
      toast.error("Falha ao excluir funil");
    }
  };

  const TABS: { key: ChannelTab; label: string; count: number }[] = [
    { key: "all", label: "Todos", count: counts.all },
    { key: "whatsapp", label: "WhatsApp", count: counts.whatsapp },
    { key: "instagram", label: "Instagram", count: counts.instagram },
  ];

  return (
    <div className="-m-6 flex h-[calc(100vh-3.5rem)] flex-col bg-background">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-card px-4 py-3 lg:px-6">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 shrink-0 text-primary" />
          <Select
            value={activeId != null ? String(activeId) : ""}
            onValueChange={(v) => setActiveId(Number(v))}
          >
            <SelectTrigger className="h-9 w-52 font-semibold">
              <SelectValue placeholder="Funil" />
            </SelectTrigger>
            <SelectContent>
              {pipelines.map((p) => (
                <SelectItem key={p.id} value={String(p.id)}>
                  {p.name}
                  {p.is_default ? " (Principal)" : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="icon"
            className="h-9 w-9"
            title="Editar etapas"
            onClick={() => setEditorOpen(true)}
            disabled={!active}
          >
            <Settings2 className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-9"
            onClick={() => {
              setFunnelName("");
              setCreateOpen(true);
            }}
          >
            <Plus className="mr-1.5 h-4 w-4" /> Novo funil
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-9 w-9" disabled={!active}>
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-44">
              <DropdownMenuItem
                onClick={() => {
                  setFunnelName(active?.name || "");
                  setRenameOpen(true);
                }}
              >
                <Pencil className="mr-2 h-4 w-4" /> Renomear funil
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => setDeleteOpen(true)}
                disabled={!active || active.is_default}
                className="text-destructive focus:text-destructive"
              >
                <Trash2 className="mr-2 h-4 w-4" /> Excluir funil
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <div className="flex items-center gap-2">
          {/* Filtro por canal */}
          <div className="flex gap-1 rounded-lg bg-muted p-1">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                  tab === t.key
                    ? "bg-card text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {t.key === "whatsapp" && <BrandWhatsApp size={14} bare />}
                {t.key === "instagram" && <BrandInstagram size={14} />}
                {t.label}
                <span className="rounded-full bg-background/70 px-1.5 text-[10px]">{t.count}</span>
              </button>
            ))}
          </div>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar lead…"
              className="h-9 w-40 pl-8 lg:w-52"
            />
          </div>
          <Button
            size="icon"
            variant="outline"
            className="h-9 w-9"
            onClick={() => activeId != null && loadCards(activeId)}
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Board */}
      <div className="flex-1 overflow-x-auto overflow-y-hidden p-4 lg:p-6">
        {loading ? (
          <div className="flex gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-[70vh] w-[270px] shrink-0 animate-pulse rounded-xl bg-muted" />
            ))}
          </div>
        ) : columns.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhuma coluna configurada no funil.</p>
        ) : (
          <DragDropContext onDragEnd={onDragEnd}>
            <div className="flex h-full w-full gap-3">
              {columns.map((col) => (
                <KanbanColumn
                  key={col.key}
                  columnKey={col.key}
                  label={col.label}
                  color={col.color}
                  cards={cardsByStatus(col.key)}
                  onCardClick={setSelected}
                />
              ))}
            </div>
          </DragDropContext>
        )}
      </div>

      <LeadDetailSheet
        card={selected}
        columns={columns}
        onClose={() => setSelected(null)}
        onChanged={applyChanged}
      />

      <ColumnEditorDialog
        open={editorOpen}
        onOpenChange={setEditorOpen}
        pipeline={active}
        onSaved={(p) => {
          applyPipeline(p);
          if (activeId != null) loadCards(activeId);
        }}
      />

      {/* Criar funil */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Novo funil</DialogTitle>
          </DialogHeader>
          <div className="space-y-1">
            <Label htmlFor="funnel-new">Nome do funil</Label>
            <Input
              id="funnel-new"
              value={funnelName}
              onChange={(e) => setFunnelName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              placeholder="Ex: Funil Instagram"
              autoFocus
            />
            <p className="text-[11px] text-muted-foreground">
              Criado com as 6 etapas padrão — personalize depois em “Editar etapas”.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)} disabled={savingFunnel}>
              Cancelar
            </Button>
            <Button onClick={handleCreate} disabled={savingFunnel || !funnelName.trim()}>
              {savingFunnel ? "Criando…" : "Criar funil"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Renomear funil */}
      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Renomear funil</DialogTitle>
          </DialogHeader>
          <div className="space-y-1">
            <Label htmlFor="funnel-rename">Nome do funil</Label>
            <Input
              id="funnel-rename"
              value={funnelName}
              onChange={(e) => setFunnelName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleRename()}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameOpen(false)} disabled={savingFunnel}>
              Cancelar
            </Button>
            <Button onClick={handleRename} disabled={savingFunnel || !funnelName.trim()}>
              {savingFunnel ? "Salvando…" : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Excluir funil */}
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir funil {active?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              Os contatos deste funil voltam para o <strong>funil padrão</strong> na etapa
              “Novos Contatos”. As etapas deste funil são descartadas. <strong>Irreversível.</strong>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Excluir funil
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
