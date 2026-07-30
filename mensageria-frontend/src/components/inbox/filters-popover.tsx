"use client";

import { Filter } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  tagColorClasses,
  type AssignableUser,
  type ContactTag,
} from "@/lib/api-inbox";
import { cn } from "@/lib/utils";

export type AiFilter = "all" | "on" | "off";

export interface InboxFilters {
  tagIds: number[];
  unreadOnly: boolean;
  ai: AiFilter;
  sdr: number | null;
}

export const EMPTY_FILTERS: InboxFilters = {
  tagIds: [],
  unreadOnly: false,
  ai: "all",
  sdr: null,
};

export function countActiveFilters(f: InboxFilters): number {
  return (
    (f.tagIds.length > 0 ? 1 : 0) +
    (f.unreadOnly ? 1 : 0) +
    (f.ai !== "all" ? 1 : 0) +
    (f.sdr !== null ? 1 : 0)
  );
}

interface Props {
  filters: InboxFilters;
  onChange: (f: InboxFilters) => void;
  allTags: ContactTag[];
  users: AssignableUser[];
}

export function FiltersPopover({ filters, onChange, allTags, users }: Props) {
  const active = countActiveFilters(filters);

  const toggleTag = (id: number) =>
    onChange({
      ...filters,
      tagIds: filters.tagIds.includes(id)
        ? filters.tagIds.filter((t) => t !== id)
        : [...filters.tagIds, id],
    });

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-9 shrink-0 gap-1.5">
          <Filter className="h-3.5 w-3.5" />
          {active > 0 && (
            <span className="rounded-full bg-primary px-1.5 text-[10px] text-primary-foreground">
              {active}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="wa-theme w-72"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-2 py-1.5">
          <DropdownMenuLabel className="p-0 text-xs">Filtros</DropdownMenuLabel>
          {active > 0 && (
            <button
              onClick={() => onChange(EMPTY_FILTERS)}
              className="text-[11px] text-muted-foreground hover:text-foreground"
            >
              Limpar
            </button>
          )}
        </div>
        <DropdownMenuSeparator />

        <div className="space-y-3 p-2">
          {/* Não lidas */}
          <div className="flex items-center justify-between">
            <Label className="text-xs">Só não lidas</Label>
            <Switch
              checked={filters.unreadOnly}
              onCheckedChange={(v) => onChange({ ...filters, unreadOnly: v })}
            />
          </div>

          {/* IA */}
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Atendimento por IA</Label>
            <div className="flex gap-1">
              {(
                [
                  ["all", "Todos"],
                  ["on", "Ligada"],
                  ["off", "Desligada"],
                ] as [AiFilter, string][]
              ).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => onChange({ ...filters, ai: key })}
                  className={cn(
                    "flex-1 rounded-md px-2 py-1 text-[11px] transition-colors",
                    filters.ai === key
                      ? "bg-primary/10 text-primary"
                      : "bg-muted text-muted-foreground hover:bg-muted/70",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* SDR */}
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Responsável</Label>
            <div className="flex flex-wrap gap-1">
              <button
                onClick={() => onChange({ ...filters, sdr: null })}
                className={cn(
                  "rounded-full px-2 py-0.5 text-[11px] transition-colors",
                  filters.sdr === null
                    ? "bg-primary/10 text-primary"
                    : "bg-muted text-muted-foreground hover:bg-muted/70",
                )}
              >
                Todos
              </button>
              {users.map((u) => (
                <button
                  key={u.id}
                  onClick={() => onChange({ ...filters, sdr: u.id })}
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[11px] transition-colors",
                    filters.sdr === u.id
                      ? "bg-primary/10 text-primary"
                      : "bg-muted text-muted-foreground hover:bg-muted/70",
                  )}
                >
                  {u.name}
                </button>
              ))}
            </div>
          </div>

          {/* Tags */}
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Tags</Label>
            {allTags.length === 0 ? (
              <div className="text-[11px] text-muted-foreground">
                Nenhuma tag criada ainda.
              </div>
            ) : (
              <div className="flex flex-wrap gap-1">
                {allTags.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => toggleTag(t.id)}
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[11px] transition-opacity",
                      tagColorClasses[t.color] ?? tagColorClasses.blue,
                      filters.tagIds.includes(t.id)
                        ? "ring-2 ring-primary ring-offset-1"
                        : "opacity-60 hover:opacity-100",
                    )}
                  >
                    {t.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
