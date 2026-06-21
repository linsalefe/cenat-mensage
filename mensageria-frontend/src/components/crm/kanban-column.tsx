"use client";

import { Droppable, Draggable } from "@hello-pangea/dnd";
import { Users } from "lucide-react";

import { KanbanCard } from "@/components/crm/kanban-card";
import type { KanbanCard as Card } from "@/types/api";

function hexToRgba(hex: string, alpha: number): string {
  const c = hex.replace("#", "");
  const r = parseInt(c.substring(0, 2), 16);
  const g = parseInt(c.substring(2, 4), 16);
  const b = parseInt(c.substring(4, 6), 16);
  if (isNaN(r) || isNaN(g) || isNaN(b)) return `rgba(100,100,100,${alpha})`;
  return `rgba(${r},${g},${b},${alpha})`;
}

export function KanbanColumn({
  columnKey,
  label,
  color,
  cards,
  onCardClick,
}: {
  columnKey: string;
  label: string;
  color: string;
  cards: Card[];
  onCardClick: (c: Card) => void;
}) {
  return (
    <div className="flex h-full w-[270px] shrink-0 flex-col">
      <div className="mb-2 rounded-xl border border-border/40 bg-muted/50 px-3.5 py-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: color }} />
            <span className="truncate text-[12px] font-medium text-foreground">{label}</span>
          </div>
          <span className="text-[11px] tabular-nums text-muted-foreground">{cards.length}</span>
        </div>
      </div>

      <Droppable droppableId={columnKey}>
        {(provided, snapshot) => (
          <div
            ref={provided.innerRef}
            {...provided.droppableProps}
            className="min-h-[120px] flex-1 space-y-2 overflow-y-auto rounded-xl p-2 transition-all duration-200"
            style={
              snapshot.isDraggingOver
                ? {
                    background: `linear-gradient(180deg, ${hexToRgba(color, 0.08)}, ${hexToRgba(color, 0.02)})`,
                    border: `2px dashed ${hexToRgba(color, 0.35)}`,
                  }
                : { border: "2px dashed transparent" }
            }
          >
            {cards.length === 0 && !snapshot.isDraggingOver && (
              <div className="py-8 text-center">
                <div
                  className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-xl"
                  style={{ background: hexToRgba(color, 0.06) }}
                >
                  <Users className="h-4 w-4" style={{ color, opacity: 0.35 }} />
                </div>
                <p className="text-[11px] text-muted-foreground/50">Nenhum contato</p>
              </div>
            )}
            {cards.map((card, idx) => (
              <Draggable key={card.id} draggableId={String(card.id)} index={idx}>
                {(prov, snap) => (
                  <div ref={prov.innerRef} {...prov.draggableProps} {...prov.dragHandleProps}>
                    <KanbanCard
                      card={card}
                      onClick={() => onCardClick(card)}
                      isDragging={snap.isDragging}
                    />
                  </div>
                )}
              </Draggable>
            ))}
            {provided.placeholder}
          </div>
        )}
      </Droppable>
    </div>
  );
}
