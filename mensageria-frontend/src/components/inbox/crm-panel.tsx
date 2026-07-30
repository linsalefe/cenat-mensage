"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Plus, Sparkles, Tag as TagIcon, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
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
import {
  inboxApi,
  tagColorClasses,
  TAG_COLORS,
  type AssignableUser,
  type ContactTag,
} from "@/lib/api-inbox";
import { cn } from "@/lib/utils";
import type { Contact, PipelineColumn } from "@/types/api";

const NO_SDR = "__none__";
/** Debounce das notas: salvar a cada tecla seria um PATCH por caractere. */
const NOTES_DEBOUNCE_MS = 800;

interface Props {
  contact: Contact;
  stageColumns: PipelineColumn[];
  allTags: ContactTag[];
  users: AssignableUser[];
  onChangeStage: (status: string) => void;
  /** Aplica a mudança no contato selecionado e na lista. */
  onPatched: (patch: Partial<Contact>) => void;
  onTagsChanged: () => void;
  onClose: () => void;
}

export function CrmPanel({
  contact,
  stageColumns,
  allTags,
  users,
  onChangeStage,
  onPatched,
  onTagsChanged,
  onClose,
}: Props) {
  const [notes, setNotes] = useState(contact.notes ?? "");

  /** Linhas de nota escritas pelo agente, extraídas para exibição destacada.
   *  Os prefixos espelham o que o backend grava: "[LEAD PÓS]" em
   *  encaminhar_comercial_pos e "🤖→👤"/"🛡️→👤" nos handoffs. */
  const agentNotes = useMemo(() => {
    const linhas = (contact.notes ?? "").split("\n");
    const out: Array<{ kind: "lead_pos" | "handoff"; text: string }> = [];
    for (const raw of linhas) {
      const linha = raw.trim();
      if (!linha) continue;
      if (linha.includes("[LEAD PÓS]")) {
        out.push({ kind: "lead_pos", text: linha.split("[LEAD PÓS]")[1]?.trim() || linha });
      } else if (linha.includes("→👤") || /Handoff/i.test(linha)) {
        out.push({ kind: "handoff", text: linha.replace(/^\[[^\]]*\]\s*/, "").replace(/^[^A-Za-zÀ-ÿ]*/, "") });
      }
    }
    return out;
  }, [contact.notes]);
  const [savingNotes, setSavingNotes] = useState(false);
  const [newTagName, setNewTagName] = useState("");
  const [newTagColor, setNewTagColor] = useState<string>(TAG_COLORS[0]);
  const [creatingTag, setCreatingTag] = useState(false);
  // Confirmação em dois passos: aninhar um AlertDialog dentro do DropdownMenu
  // fecharia o menu ao abrir o diálogo.
  const [pendingDelete, setPendingDelete] = useState<number | null>(null);
  const notesTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const contactIdRef = useRef(contact.id);

  // Trocar de conversa descarta o debounce pendente — senão a nota de um contato
  // vazaria para o outro.
  useEffect(() => {
    if (contactIdRef.current !== contact.id) {
      if (notesTimer.current) clearTimeout(notesTimer.current);
      contactIdRef.current = contact.id;
      setNotes(contact.notes ?? "");
    }
  }, [contact.id, contact.notes]);

  useEffect(() => {
    return () => {
      if (notesTimer.current) clearTimeout(notesTimer.current);
    };
  }, []);

  const saveNotes = (value: string) => {
    const id = contact.id;
    if (notesTimer.current) clearTimeout(notesTimer.current);
    notesTimer.current = setTimeout(async () => {
      setSavingNotes(true);
      try {
        await inboxApi.patchContact(id, { notes: value });
        onPatched({ notes: value });
      } catch {
        toast.error("Falha ao salvar as notas");
      } finally {
        setSavingNotes(false);
      }
    }, NOTES_DEBOUNCE_MS);
  };

  const toggleAI = async () => {
    const next = !contact.ai_active;
    onPatched({ ai_active: next }); // otimista
    try {
      await inboxApi.patchContact(contact.id, { ai_active: next });
    } catch {
      toast.error("Falha ao alterar a IA");
      onPatched({ ai_active: !next });
    }
  };

  const changeSdr = async (value: string) => {
    const next = value === NO_SDR ? null : Number(value);
    const prev = contact.assigned_to;
    onPatched({ assigned_to: next });
    try {
      await inboxApi.patchContact(contact.id, { assigned_to: next });
    } catch {
      toast.error("Falha ao alterar o responsável");
      onPatched({ assigned_to: prev });
    }
  };

  const attachTag = async (tag: ContactTag) => {
    if (contact.tags.some((t) => t.id === tag.id)) return;
    onPatched({ tags: [...contact.tags, tag] });
    try {
      await inboxApi.addTag(contact.id, tag.id);
      onTagsChanged();
    } catch {
      toast.error("Falha ao aplicar a tag");
      onPatched({ tags: contact.tags.filter((t) => t.id !== tag.id) });
    }
  };

  const detachTag = async (tag: ContactTag) => {
    const prev = contact.tags;
    onPatched({ tags: prev.filter((t) => t.id !== tag.id) });
    try {
      await inboxApi.removeTag(contact.id, tag.id);
      onTagsChanged();
    } catch {
      toast.error("Falha ao remover a tag");
      onPatched({ tags: prev });
    }
  };

  const destroyTag = async (tag: ContactTag) => {
    setPendingDelete(null);
    try {
      await inboxApi.deleteTag(tag.id);
      // O vínculo cai por ON DELETE CASCADE; tira do contato aberto na hora.
      onPatched({ tags: contact.tags.filter((t) => t.id !== tag.id) });
      onTagsChanged();
      toast.success(`Tag "${tag.name}" excluída`);
    } catch {
      toast.error("Falha ao excluir a tag");
    }
  };

  const createTag = async () => {
    const name = newTagName.trim();
    if (!name) return;
    setCreatingTag(true);
    try {
      const tag = await inboxApi.createTag(name, newTagColor);
      setNewTagName("");
      onTagsChanged();
      await attachTag(tag);
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Falha ao criar a tag");
    } finally {
      setCreatingTag(false);
    }
  };

  return (
    <aside className="flex w-full shrink-0 flex-col overflow-y-auto border-l border-border bg-card lg:w-[300px]">
      <div className="flex items-center justify-between border-b border-border p-3">
        <h2 className="text-sm font-semibold">Detalhes do contato</h2>
        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="space-y-5 p-4">
        {/* Etapa */}
        {stageColumns.length > 0 && (
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Etapa do funil</Label>
            <Select value={contact.lead_status || "novo"} onValueChange={onChangeStage}>
              <SelectTrigger className="h-9 text-xs">
                <SelectValue placeholder="Etapa" />
              </SelectTrigger>
              <SelectContent className="wa-theme">
                {stageColumns.map((col) => (
                  <SelectItem key={col.key} value={col.key} className="text-xs">
                    {col.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {/* Responsável */}
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Responsável (SDR)</Label>
          <Select
            value={contact.assigned_to ? String(contact.assigned_to) : NO_SDR}
            onValueChange={changeSdr}
          >
            <SelectTrigger className="h-9 text-xs">
              <SelectValue placeholder="Ninguém" />
            </SelectTrigger>
            <SelectContent className="wa-theme">
              <SelectItem value={NO_SDR} className="text-xs">
                Ninguém
              </SelectItem>
              {users.map((u) => (
                <SelectItem key={u.id} value={String(u.id)} className="text-xs">
                  {u.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* IA */}
        <div className="flex items-center justify-between rounded-lg border border-border p-3">
          <div className="flex items-center gap-2">
            <Sparkles
              className={cn(
                "h-4 w-4",
                contact.ai_active ? "text-emerald-500" : "text-muted-foreground",
              )}
            />
            <div>
              <div className="text-xs font-medium">Atendimento por IA</div>
              <div className="text-[11px] text-muted-foreground">
                {contact.ai_active ? "Respondendo sozinha" : "Desligada"}
              </div>
            </div>
          </div>
          <Switch checked={contact.ai_active} onCheckedChange={toggleAI} />
        </div>

        {/* Tags */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-xs text-muted-foreground">Tags</Label>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="ghost" className="h-6 gap-1 px-1.5 text-xs">
                  <Plus className="h-3 w-3" />
                  Adicionar
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="wa-theme w-72">
                <DropdownMenuLabel className="text-xs">Tags existentes</DropdownMenuLabel>
                {allTags.length === 0 && (
                  <div className="px-2 py-1.5 text-xs text-muted-foreground">
                    Nenhuma tag criada ainda.
                  </div>
                )}
                {allTags.map((t) => {
                  const applied = contact.tags.some((ct) => ct.id === t.id);
                  const confirming = pendingDelete === t.id;
                  return (
                    <div
                      key={t.id}
                      className="flex items-center gap-1 px-2 py-1"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        onClick={() => (applied ? detachTag(t) : attachTag(t))}
                        className="flex flex-1 items-center gap-2 text-left"
                      >
                        <span
                          className={cn(
                            "rounded-full px-2 py-0.5 text-[11px]",
                            tagColorClasses[t.color] ?? tagColorClasses.blue,
                          )}
                        >
                          {t.name}
                        </span>
                        {applied && <Check className="h-3 w-3 text-primary" />}
                      </button>

                      {confirming ? (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => destroyTag(t)}
                            className="rounded px-1.5 py-0.5 text-[10px] font-medium text-destructive hover:bg-destructive/10"
                          >
                            Excluir
                          </button>
                          <button
                            onClick={() => setPendingDelete(null)}
                            className="rounded px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-muted"
                          >
                            Cancelar
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setPendingDelete(t.id)}
                          aria-label={`Excluir a tag ${t.name}`}
                          title="Excluir de todos os contatos"
                          className="p-1 text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  );
                })}
                <DropdownMenuSeparator />
                <DropdownMenuLabel className="text-xs">Criar nova</DropdownMenuLabel>
                <div
                  className="space-y-2 p-2"
                  // O dropdown fecharia ao clicar no input.
                  onClick={(e) => e.stopPropagation()}
                  onKeyDown={(e) => e.stopPropagation()}
                >
                  <Input
                    value={newTagName}
                    onChange={(e) => setNewTagName(e.target.value)}
                    placeholder="Nome da tag"
                    className="h-8 text-xs"
                  />
                  <div className="flex gap-1">
                    {TAG_COLORS.map((c) => (
                      <button
                        key={c}
                        aria-label={`Cor ${c}`}
                        onClick={() => setNewTagColor(c)}
                        className={cn(
                          "flex h-6 w-6 items-center justify-center rounded-full",
                          tagColorClasses[c],
                          newTagColor === c && "ring-2 ring-primary ring-offset-1",
                        )}
                      >
                        {newTagColor === c && <Check className="h-3 w-3" />}
                      </button>
                    ))}
                  </div>
                  <Button
                    size="sm"
                    className="h-7 w-full text-xs"
                    disabled={!newTagName.trim() || creatingTag}
                    onClick={createTag}
                  >
                    Criar e aplicar
                  </Button>
                </div>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          {contact.tags.length === 0 ? (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <TagIcon className="h-3.5 w-3.5" />
              Sem tags.
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {contact.tags.map((t) => (
                <span
                  key={t.id}
                  className={cn(
                    "group flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px]",
                    tagColorClasses[t.color] ?? tagColorClasses.blue,
                  )}
                >
                  {t.name}
                  <button
                    aria-label={`Remover tag ${t.name}`}
                    onClick={() => detachTag(t)}
                    className="opacity-60 transition-opacity hover:opacity-100"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Notas */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label className="text-xs text-muted-foreground">Notas</Label>
            {savingNotes && (
              <span className="text-[10px] text-muted-foreground">salvando…</span>
            )}
          </div>

          {/* Linhas escritas pelo agente (lead de pós e handoff) em destaque:
              no textarea elas se perdem no meio das anotações manuais, e são
              justamente o que o atendente precisa ver ao assumir a conversa. */}
          {agentNotes.length > 0 && (
            <div className="space-y-1">
              {agentNotes.map((linha, i) => (
                <div
                  key={i}
                  className={cn(
                    "rounded-md border px-2 py-1.5 text-[11px] leading-snug",
                    linha.kind === "lead_pos"
                      ? "border-accent/40 bg-accent/10 text-accent"
                      : "border-amber-500/40 bg-amber-500/10 text-amber-300",
                  )}
                >
                  <span className="font-semibold">
                    {linha.kind === "lead_pos" ? "🎓 Lead de pós" : "🤖→👤 Handoff"}
                  </span>{" "}
                  <span className="opacity-90">{linha.text}</span>
                </div>
              ))}
            </div>
          )}

          <Textarea
            value={notes}
            onChange={(e) => {
              setNotes(e.target.value);
              saveNotes(e.target.value);
            }}
            placeholder="Anotações internas sobre este contato…"
            rows={5}
            className="resize-none text-xs"
          />
        </div>
      </div>
    </aside>
  );
}
