"use client";

import { Clock } from "lucide-react";

import { ChannelIcon } from "@/components/brand/channel-icon";
import { cn } from "@/lib/utils";
import type { KanbanCard as Card } from "@/types/api";

export function stripIg(waId: string) {
  return waId.startsWith("ig:") ? waId.slice(3) : waId;
}

export function cardName(c: Card) {
  return c.name && c.name.trim() ? c.name : stripIg(c.wa_id);
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/);
  if (!parts[0]) return "?";
  if (parts.length === 1) return parts[0][0].toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const AVATAR_COLORS = [
  "bg-emerald-500",
  "bg-teal-500",
  "bg-sky-500",
  "bg-violet-500",
  "bg-fuchsia-500",
  "bg-amber-500",
  "bg-rose-500",
];

export function avatarColor(seed: string) {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

function relTime(d: string | null): string {
  if (!d) return "";
  const date = new Date(d);
  if (isNaN(date.getTime())) return "";
  const min = Math.floor((Date.now() - date.getTime()) / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `${min}min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function cleanNotes(notes: string | null): string | null {
  if (!notes) return null;
  const t = notes.trim();
  if (t.startsWith("{") || t.startsWith("[") || t.length < 3) return null;
  return t;
}

export function KanbanCard({
  card,
  onClick,
  isDragging = false,
}: {
  card: Card;
  onClick: () => void;
  isDragging?: boolean;
}) {
  const name = cardName(card);
  const notes = cleanNotes(card.notes);
  const time = relTime(card.last_inbound_at || card.updated_at);

  return (
    <div
      onClick={onClick}
      className={cn(
        "group relative cursor-grab select-none rounded-xl border border-border/60 bg-card transition-all duration-200 active:cursor-grabbing",
        isDragging ? "rotate-[1.5deg] scale-[0.97] opacity-90 shadow-xl" : "hover:-translate-y-0.5 hover:shadow-md",
      )}
    >
      <div className="space-y-2.5 p-3">
        <div className="flex items-center gap-2.5">
          <div className="relative shrink-0">
            <div
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-lg text-[11px] font-semibold text-white",
                avatarColor(name),
              )}
            >
              {initials(name)}
            </div>
            <span className="absolute -bottom-1 -right-1 rounded-full bg-card p-0.5">
              <ChannelIcon provider={card.provider} size={13} />
            </span>
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-semibold text-foreground" title={name}>
              {name}
            </p>
            {time && (
              <span className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
                <Clock className="h-2.5 w-2.5" />
                {time}
              </span>
            )}
          </div>
          {card.deal_value ? (
            <span className="shrink-0 rounded-md bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
              {BRL.format(card.deal_value)}
            </span>
          ) : null}
        </div>
        {notes && (
          <p className="line-clamp-1 pl-[42px] text-[11px] leading-relaxed text-muted-foreground">
            {notes}
          </p>
        )}
      </div>
    </div>
  );
}
