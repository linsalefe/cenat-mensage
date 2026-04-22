'use client';

import { memo, useState } from 'react';
import {
  BaseEdge, EdgeLabelRenderer, getSmoothStepPath, useReactFlow,
  type EdgeProps, type Node,
} from '@xyflow/react';
import { Plus, Check, X as XIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { NODE_META, type NodeKind, createDefaultNodeData, PALETTE_ORDER } from './node-catalog';

// Cores de stroke por tipo de nó origem (hex puro pra SVG)
const SOURCE_COLOR: Record<NodeKind, string> = {
  trigger: '#8b5cf6',
  message: '#3b82f6',
  buttons: '#6366f1',
  input: '#06b6d4',
  condition: '#f59e0b',
  tag: '#ec4899',
  move_stage: '#14b8a6',
  delay: '#eab308',
  handoff: '#f97316',
  end: '#6b7280',
  http_request: '#0ea5e9',
  webhook_out: '#d946ef',
};

function CustomEdge(props: EdgeProps) {
  const {
    id, sourceX, sourceY, targetX, targetY,
    sourcePosition, targetPosition,
    source, sourceHandleId, selected, markerEnd,
  } = props;

  const { getNode, setNodes, setEdges } = useReactFlow();
  const [hovered, setHovered] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX, sourceY, targetX, targetY,
    sourcePosition, targetPosition,
    borderRadius: 16,
  });

  const sourceNode = getNode(source) as Node | undefined;
  const sourceKind = (sourceNode?.type || 'message') as NodeKind;
  const strokeColor = SOURCE_COLOR[sourceKind] || '#94a3b8';

  // Label contextual (botões mostra label do botão; condição mostra check/x)
  let label: React.ReactNode = null;
  if (sourceNode?.type === 'buttons' && sourceHandleId) {
    const btn = (sourceNode.data as any)?.buttons?.find((b: any) => b.id === sourceHandleId);
    if (btn?.label) {
      label = (
        <span className="px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 text-[10px] font-medium border border-indigo-500/20 whitespace-nowrap max-w-[140px] truncate">
          {btn.label}
        </span>
      );
    }
  } else if (sourceNode?.type === 'condition' && sourceHandleId) {
    if (sourceHandleId === 'true') {
      label = (
        <span className="w-5 h-5 rounded-full bg-emerald-500 text-white flex items-center justify-center shadow-sm">
          <Check className="w-3 h-3" strokeWidth={3} />
        </span>
      );
    } else if (sourceHandleId === 'false') {
      label = (
        <span className="w-5 h-5 rounded-full bg-rose-500 text-white flex items-center justify-center shadow-sm">
          <XIcon className="w-3 h-3" strokeWidth={3} />
        </span>
      );
    }
  } else if (sourceNode?.type === 'http_request' && sourceHandleId) {
    if (sourceHandleId === 'success') {
      label = (
        <span className="w-5 h-5 rounded-full bg-emerald-500 text-white flex items-center justify-center shadow-sm">
          <Check className="w-3 h-3" strokeWidth={3} />
        </span>
      );
    } else if (sourceHandleId === 'error') {
      label = (
        <span className="w-5 h-5 rounded-full bg-rose-500 text-white flex items-center justify-center shadow-sm">
          <XIcon className="w-3 h-3" strokeWidth={3} />
        </span>
      );
    }
  }

  const handleInsertNode = (kind: NodeKind) => {
    setMenuOpen(false);
    const newNodeId = `${kind}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    const newNode: Node = {
      id: newNodeId,
      type: kind,
      position: { x: labelX - 110, y: labelY - 40 },
      data: createDefaultNodeData(kind),
    };

    // Split do edge: A→B vira A→new→B
    setNodes((nds) => nds.concat(newNode));
    setEdges((eds) => {
      const original = eds.find((e) => e.id === id);
      if (!original) return eds;
      const rest = eds.filter((e) => e.id !== id);
      return rest.concat([
        {
          id: `${original.source}-${newNodeId}`,
          source: original.source,
          sourceHandle: original.sourceHandle,
          target: newNodeId,
          type: 'custom',
          animated: true,
          markerEnd: original.markerEnd,
        },
        {
          id: `${newNodeId}-${original.target}`,
          source: newNodeId,
          target: original.target,
          targetHandle: original.targetHandle,
          type: 'custom',
          animated: true,
          markerEnd: original.markerEnd,
        },
      ]);
    });
  };

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: strokeColor,
          strokeWidth: selected ? 2.5 : 1.8,
          opacity: selected ? 1 : 0.85,
        }}
      />

      {/* Invisible wider path for hover */}
      <path
        d={edgePath}
        stroke="transparent"
        strokeWidth={20}
        fill="none"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        className="cursor-pointer"
      />

      <EdgeLabelRenderer>
        <div
          className="pointer-events-auto absolute flex items-center gap-1"
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
          }}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
        >
          {label}

          {(hovered || menuOpen) && (
            <div className="relative">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setMenuOpen((v) => !v);
                }}
                className={cn(
                  'w-6 h-6 rounded-full flex items-center justify-center shadow-md transition-all',
                  menuOpen
                    ? 'bg-primary text-primary-foreground scale-110'
                    : 'bg-card border-2 border-primary text-primary hover:bg-primary hover:text-primary-foreground',
                )}
                aria-label="Inserir nó aqui"
              >
                <Plus className="w-3.5 h-3.5" strokeWidth={2.5} />
              </button>

              {menuOpen && (
                <div
                  className="absolute left-1/2 -translate-x-1/2 mt-2 w-56 rounded-lg bg-popover border border-border shadow-xl py-1 z-50"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="px-3 py-1.5 text-[10px] uppercase font-semibold tracking-wider text-muted-foreground">
                    Inserir nó aqui
                  </div>
                  {PALETTE_ORDER.filter((k) => k !== 'trigger').map((kind) => {
                    const meta = NODE_META[kind];
                    const Icon = meta.icon;
                    return (
                      <button
                        key={kind}
                        onClick={() => handleInsertNode(kind)}
                        className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-muted text-left transition-colors"
                      >
                        <div className={cn('w-6 h-6 rounded-md flex items-center justify-center', meta.colorClass)}>
                          <Icon className="w-3.5 h-3.5" />
                        </div>
                        <span className="text-foreground">{meta.label}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

export const edgeTypes = {
  custom: memo(CustomEdge),
};
