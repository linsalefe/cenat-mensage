'use client';

import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import {
  Zap, MessageSquare, MousePointerClick, TextCursorInput,
  GitBranch, Tag, ArrowRightLeft, UserCheck, Flag, Timer, Globe, Send,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// ============================================================
// Metadata por tipo de nó
// ============================================================
export type NodeKind =
  | 'trigger' | 'message' | 'buttons' | 'input' | 'condition'
  | 'tag' | 'move_stage' | 'delay' | 'handoff' | 'end' | 'http_request' | 'webhook_out';

export const NODE_META: Record<NodeKind, {
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  colorClass: string;
  borderClass: string;
  accentClass: string;
}> = {
  trigger: {
    label: 'Gatilho',
    description: 'Início do fluxo',
    icon: Zap,
    colorClass: 'bg-violet-500/10 text-violet-600 dark:text-violet-400',
    borderClass: 'border-violet-500/30',
    accentClass: 'bg-violet-500',
  },
  message: {
    label: 'Mensagem',
    description: 'Envia texto',
    icon: MessageSquare,
    colorClass: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
    borderClass: 'border-blue-500/30',
    accentClass: 'bg-blue-500',
  },
  buttons: {
    label: 'Botões',
    description: 'Oferece escolhas',
    icon: MousePointerClick,
    colorClass: 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400',
    borderClass: 'border-indigo-500/30',
    accentClass: 'bg-indigo-500',
  },
  input: {
    label: 'Captura',
    description: 'Pergunta e guarda',
    icon: TextCursorInput,
    colorClass: 'bg-cyan-500/10 text-cyan-600 dark:text-cyan-400',
    borderClass: 'border-cyan-500/30',
    accentClass: 'bg-cyan-500',
  },
  condition: {
    label: 'Condição',
    description: 'Se / Então',
    icon: GitBranch,
    colorClass: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
    borderClass: 'border-amber-500/30',
    accentClass: 'bg-amber-500',
  },
  tag: {
    label: 'Tag',
    description: 'Marca o contato',
    icon: Tag,
    colorClass: 'bg-pink-500/10 text-pink-600 dark:text-pink-400',
    borderClass: 'border-pink-500/30',
    accentClass: 'bg-pink-500',
  },
  move_stage: {
    label: 'Mover Kanban',
    description: 'Muda coluna',
    icon: ArrowRightLeft,
    colorClass: 'bg-teal-500/10 text-teal-600 dark:text-teal-400',
    borderClass: 'border-teal-500/30',
    accentClass: 'bg-teal-500',
  },
  delay: {
    label: 'Espera',
    description: 'Pausa por tempo',
    icon: Timer,
    colorClass: 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400',
    borderClass: 'border-yellow-500/30',
    accentClass: 'bg-yellow-500',
  },
  handoff: {
    label: 'Passar para humano',
    description: 'Cria tarefa + move',
    icon: UserCheck,
    colorClass: 'bg-orange-500/10 text-orange-600 dark:text-orange-400',
    borderClass: 'border-orange-500/30',
    accentClass: 'bg-orange-500',
  },
  end: {
    label: 'Fim',
    description: 'Encerra sessão',
    icon: Flag,
    colorClass: 'bg-gray-500/10 text-gray-600 dark:text-gray-400',
    borderClass: 'border-gray-500/30',
    accentClass: 'bg-gray-500',
  },
  http_request: {
    label: 'HTTP Request',
    description: 'Chama uma API',
    icon: Globe,
    colorClass: 'bg-sky-500/10 text-sky-600 dark:text-sky-400',
    borderClass: 'border-sky-500/30',
    accentClass: 'bg-sky-500',
  },
  webhook_out: {
    label: 'Webhook Out',
    description: 'Dispara notificação',
    icon: Send,
    colorClass: 'bg-fuchsia-500/10 text-fuchsia-600 dark:text-fuchsia-400',
    borderClass: 'border-fuchsia-500/30',
    accentClass: 'bg-fuchsia-500',
  },
};

export const PALETTE_ORDER: NodeKind[] = [
  'trigger', 'message', 'buttons', 'input',
  'condition', 'http_request', 'webhook_out', 'tag', 'move_stage', 'delay', 'handoff', 'end',
];

// ============================================================
// Data default por tipo
// ============================================================
export function createDefaultNodeData(kind: NodeKind): Record<string, unknown> {
  switch (kind) {
    case 'trigger':
      return { kind: 'trigger', mode: 'any_message', keyword: '' };
    case 'message':
      return { text: '' };
    case 'buttons':
      return {
        text: 'Escolha uma opção:',
        buttons: [
          { id: `b_${Math.random().toString(36).slice(2, 8)}`, label: 'Opção 1' },
          { id: `b_${Math.random().toString(36).slice(2, 8)}`, label: 'Opção 2' },
        ],
        capture_to: '',
      };
    case 'input':
      return { prompt: '', variable: '', validation: 'text', error_message: '' };
    case 'condition':
      return { variable: '', operator: 'equals', value: '' };
    case 'tag':
      return { tag_name: '' };
    case 'move_stage':
      return { stage: '' };
    case 'delay':
      return { amount: 1, unit: 'minutes' };
    case 'handoff':
      return {
        task_title: 'Atender {nome}',
        task_description: '',
        assigned_to_user_id: 0,
        stage: '',
        priority: 'media',
      };
    case 'end':
      return {};
    case 'http_request':
      return {
        method: 'GET',
        url: '',
        headers: [],
        body_mode: 'none',
        body: '',
        response_var_prefix: 'http',
      };
    case 'webhook_out':
      return {
        url: '',
        event_name: 'chatbot_event',
        payload_mode: 'auto',
        custom_payload: '',
        headers: [],
      };
  }
}

// ============================================================
// Carcaça comum
// ============================================================
function NodeShell({
  kind, selected, children, minWidth = 220,
}: {
  kind: NodeKind; selected: boolean; children: React.ReactNode; minWidth?: number;
}) {
  const meta = NODE_META[kind];
  const Icon = meta.icon;
  return (
    <div
      className={cn(
        'relative rounded-xl bg-card border-2 shadow-sm transition-all hover:shadow-md',
        selected
          ? 'border-primary shadow-lg ring-2 ring-primary/20'
          : cn('border-border', meta.borderClass),
      )}
      style={{ minWidth, maxWidth: 280 }}
    >
      <div className={cn('absolute top-0 left-0 right-0 h-[3px] rounded-t-xl', meta.accentClass)} />
      <div className="p-3">
        <div className="flex items-center gap-2 mb-2">
          <div className={cn('w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0', meta.colorClass)}>
            <Icon className="w-4 h-4" />
          </div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {meta.label}
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}

function Preview({ text, placeholder }: { text: string; placeholder: string }) {
  return (
    <div className="text-xs text-foreground/80 line-clamp-2 bg-muted/40 rounded-md px-2 py-1.5 min-h-[28px]">
      {text?.trim() || <span className="text-muted-foreground italic">{placeholder}</span>}
    </div>
  );
}

// Handles laterais — maiores, destacados, com hover
const HANDLE_CLASS = '!w-3.5 !h-3.5 !border-2 !border-background transition-all hover:!w-[18px] hover:!h-[18px]';
const HANDLE_LEFT = { left: -7 };
const HANDLE_RIGHT = { right: -7 };

// ============================================================
// Componentes de nó
// ============================================================
export const TriggerNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, any>;
  const label = d.mode === 'keyword'
    ? (d.keyword ? `Quando contém: "${d.keyword}"` : 'Palavra-chave (configurar)')
    : 'Qualquer primeira mensagem';
  return (
    <NodeShell kind="trigger" selected={selected}>
      <Preview text={label} placeholder="Configure o gatilho" />
      <Handle type="source" position={Position.Right} style={HANDLE_RIGHT} className={cn(HANDLE_CLASS, '!bg-violet-500')} />
    </NodeShell>
  );
});
TriggerNode.displayName = 'TriggerNode';

export const MessageNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, any>;
  return (
    <NodeShell kind="message" selected={selected}>
      <Handle type="target" position={Position.Left} style={HANDLE_LEFT} className={cn(HANDLE_CLASS, '!bg-blue-500')} />
      <Preview text={d.text} placeholder="Clique pra escrever a mensagem" />
      <Handle type="source" position={Position.Right} style={HANDLE_RIGHT} className={cn(HANDLE_CLASS, '!bg-blue-500')} />
    </NodeShell>
  );
});
MessageNode.displayName = 'MessageNode';

export const ButtonsNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, any>;
  const buttons: Array<{ id: string; label: string }> = d.buttons || [];
  return (
    <NodeShell kind="buttons" selected={selected} minWidth={240}>
      <Handle type="target" position={Position.Left} style={HANDLE_LEFT} className={cn(HANDLE_CLASS, '!bg-indigo-500')} />
      <Preview text={d.text} placeholder="Pergunta do menu" />
      <div className="mt-2 space-y-1.5">
        {buttons.length === 0 && (
          <div className="text-xs text-muted-foreground italic px-2">Sem botões ainda</div>
        )}
        {buttons.map((btn, idx) => (
          <div key={btn.id} className="relative">
            <div className="flex items-center justify-between gap-2 text-xs bg-indigo-500/5 border border-indigo-500/20 rounded-md px-2 py-1.5">
              <span className="text-muted-foreground font-mono text-[10px]">{idx + 1}</span>
              <span className="flex-1 truncate text-foreground">{btn.label || 'Sem título'}</span>
            </div>
            <Handle
              id={btn.id}
              type="source"
              position={Position.Right}
              className={cn(HANDLE_CLASS, '!bg-indigo-500')}
              style={{ top: '50%', right: -7 }}
            />
          </div>
        ))}
      </div>
    </NodeShell>
  );
});
ButtonsNode.displayName = 'ButtonsNode';

export const InputNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, any>;
  return (
    <NodeShell kind="input" selected={selected}>
      <Handle type="target" position={Position.Left} style={HANDLE_LEFT} className={cn(HANDLE_CLASS, '!bg-cyan-500')} />
      <Preview text={d.prompt} placeholder="Pergunta para o usuário" />
      {d.variable && (
        <div className="mt-1.5 text-[11px] text-muted-foreground">
          &rarr; guarda em <code className="text-cyan-600 dark:text-cyan-400 font-mono">{`{${d.variable}}`}</code>
        </div>
      )}
      <Handle type="source" position={Position.Right} style={HANDLE_RIGHT} className={cn(HANDLE_CLASS, '!bg-cyan-500')} />
    </NodeShell>
  );
});
InputNode.displayName = 'InputNode';

export const ConditionNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, any>;
  const opLabel: Record<string, string> = { equals: '=', not_equals: '≠', contains: 'contém' };
  return (
    <NodeShell kind="condition" selected={selected} minWidth={240}>
      <Handle type="target" position={Position.Left} style={HANDLE_LEFT} className={cn(HANDLE_CLASS, '!bg-amber-500')} />
      <div className="text-xs text-foreground/80 bg-muted/40 rounded-md px-2 py-1.5 min-h-[28px] font-mono">
        {d.variable ? (
          <>
            <span className="text-amber-600 dark:text-amber-400">{`{${d.variable}}`}</span>
            {' '}<span className="text-muted-foreground">{opLabel[d.operator as string] || '='}</span>{' '}
            <span className="text-foreground">&ldquo;{d.value || '?'}&rdquo;</span>
          </>
        ) : (
          <span className="text-muted-foreground italic">Configure a condição</span>
        )}
      </div>
      <div className="flex items-center justify-between mt-2 text-[10px] font-medium">
        <span className="text-emerald-600 dark:text-emerald-400">Verdadeiro</span>
        <span className="text-rose-600 dark:text-rose-400">Falso</span>
      </div>
      {/* 2 sources verticais à direita */}
      <Handle id="true" type="source" position={Position.Right} className={cn(HANDLE_CLASS, '!bg-emerald-500')} style={{ top: '38%', right: -7 }} />
      <Handle id="false" type="source" position={Position.Right} className={cn(HANDLE_CLASS, '!bg-rose-500')} style={{ top: '72%', right: -7 }} />
    </NodeShell>
  );
});
ConditionNode.displayName = 'ConditionNode';

export const TagNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, any>;
  return (
    <NodeShell kind="tag" selected={selected}>
      <Handle type="target" position={Position.Left} style={HANDLE_LEFT} className={cn(HANDLE_CLASS, '!bg-pink-500')} />
      <Preview text={d.tag_name ? `${d.tag_name}` : ''} placeholder="Nome da tag" />
      <Handle type="source" position={Position.Right} style={HANDLE_RIGHT} className={cn(HANDLE_CLASS, '!bg-pink-500')} />
    </NodeShell>
  );
});
TagNode.displayName = 'TagNode';

export const MoveStageNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, any>;
  return (
    <NodeShell kind="move_stage" selected={selected}>
      <Handle type="target" position={Position.Left} style={HANDLE_LEFT} className={cn(HANDLE_CLASS, '!bg-teal-500')} />
      <Preview text={d.stage ? `→ ${d.stage}` : ''} placeholder="Coluna do Kanban" />
      <Handle type="source" position={Position.Right} style={HANDLE_RIGHT} className={cn(HANDLE_CLASS, '!bg-teal-500')} />
    </NodeShell>
  );
});
MoveStageNode.displayName = 'MoveStageNode';

export const DelayNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, any>;
  const amount = d.amount ?? 1;
  const unit = d.unit ?? 'minutes';
  const unitLabel: Record<string, string> = { minutes: 'min', hours: 'h', days: 'd' };
  return (
    <NodeShell kind="delay" selected={selected}>
      <Handle type="target" position={Position.Left} style={HANDLE_LEFT} className={cn(HANDLE_CLASS, '!bg-yellow-500')} />
      <Preview text={`⏳ ${amount} ${unitLabel[unit] || unit}`} placeholder="Configurar tempo" />
      <Handle type="source" position={Position.Right} style={HANDLE_RIGHT} className={cn(HANDLE_CLASS, '!bg-yellow-500')} />
    </NodeShell>
  );
});
DelayNode.displayName = 'DelayNode';

export const HandoffNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, any>;
  return (
    <NodeShell kind="handoff" selected={selected}>
      <Handle type="target" position={Position.Left} style={HANDLE_LEFT} className={cn(HANDLE_CLASS, '!bg-orange-500')} />
      <Preview text={d.task_title as string} placeholder="Título da tarefa" />
      <div className="mt-1.5 flex items-center gap-2 text-[10px] text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <UserCheck className="w-3 h-3" />
          {d.assigned_to_user_id ? `user #${d.assigned_to_user_id}` : 'sem responsável'}
        </span>
        {d.stage && <span>&middot; &rarr; {d.stage as string}</span>}
      </div>
    </NodeShell>
  );
});
HandoffNode.displayName = 'HandoffNode';

export const EndNode = memo(({ selected }: NodeProps) => {
  return (
    <NodeShell kind="end" selected={selected} minWidth={160}>
      <Handle type="target" position={Position.Left} style={HANDLE_LEFT} className={cn(HANDLE_CLASS, '!bg-gray-500')} />
      <div className="text-xs text-center text-muted-foreground py-1">Encerra o fluxo</div>
    </NodeShell>
  );
});
EndNode.displayName = 'EndNode';

export const HttpRequestNode = memo(({ data, selected }: NodeProps) => {
  const d = (data || {}) as any;
  const method = (d.method || 'GET').toUpperCase();
  const url = d.url || '';
  const methodColor: Record<string, string> = {
    GET: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
    POST: 'bg-blue-500/15 text-blue-700 dark:text-blue-400',
    PUT: 'bg-amber-500/15 text-amber-700 dark:text-amber-400',
    PATCH: 'bg-purple-500/15 text-purple-700 dark:text-purple-400',
    DELETE: 'bg-rose-500/15 text-rose-700 dark:text-rose-400',
  };
  return (
    <NodeShell kind="http_request" selected={selected} minWidth={260}>
      <Handle type="target" position={Position.Left} style={HANDLE_LEFT} className={cn(HANDLE_CLASS, '!bg-sky-500')} />
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className={cn('text-[10px] font-bold px-1.5 py-0.5 rounded', methodColor[method] || 'bg-muted text-foreground')}>
          {method}
        </span>
        <span className="text-[11px] text-foreground/80 font-mono truncate flex-1">
          {url || <span className="italic text-muted-foreground">URL não configurada</span>}
        </span>
      </div>
      <div className="flex items-center justify-between mt-2 text-[10px] font-medium">
        <span className="text-emerald-600 dark:text-emerald-400">Sucesso</span>
        <span className="text-rose-600 dark:text-rose-400">Erro</span>
      </div>
      <Handle id="success" type="source" position={Position.Right} className={cn(HANDLE_CLASS, '!bg-emerald-500')} style={{ top: '40%', right: -7 }} />
      <Handle id="error" type="source" position={Position.Right} className={cn(HANDLE_CLASS, '!bg-rose-500')} style={{ top: '74%', right: -7 }} />
    </NodeShell>
  );
});
HttpRequestNode.displayName = 'HttpRequestNode';

export const WebhookOutNode = memo(({ data, selected }: NodeProps) => {
  const d = (data || {}) as any;
  const url = d.url || '';
  const event = d.event_name || 'chatbot_event';
  return (
    <NodeShell kind="webhook_out" selected={selected} minWidth={240}>
      <Handle type="target" position={Position.Left} style={HANDLE_LEFT} className={cn(HANDLE_CLASS, '!bg-fuchsia-500')} />
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-400">
          POST
        </span>
        <span className="text-[11px] text-foreground/80 font-mono truncate flex-1">
          {url || <span className="italic text-muted-foreground">URL não configurada</span>}
        </span>
      </div>
      <div className="text-[10px] text-muted-foreground truncate">
        evento: <code className="font-mono text-fuchsia-600 dark:text-fuchsia-400">{event}</code>
      </div>
      <div className="mt-1.5 text-[10px] text-muted-foreground italic">
        fire-and-forget
      </div>
      <Handle type="source" position={Position.Right} style={HANDLE_RIGHT} className={cn(HANDLE_CLASS, '!bg-fuchsia-500')} />
    </NodeShell>
  );
});
WebhookOutNode.displayName = 'WebhookOutNode';

// ============================================================
// nodeTypes para <ReactFlow>
// ============================================================
export const nodeTypes = {
  trigger: TriggerNode,
  message: MessageNode,
  buttons: ButtonsNode,
  input: InputNode,
  condition: ConditionNode,
  tag: TagNode,
  move_stage: MoveStageNode,
  delay: DelayNode,
  handoff: HandoffNode,
  end: EndNode,
  http_request: HttpRequestNode,
  webhook_out: WebhookOutNode,
};

// ============================================================
// Paleta lateral esquerda
// ============================================================
export function NodePalette() {
  const onDragStart = (event: React.DragEvent, kind: NodeKind) => {
    event.dataTransfer.setData('application/reactflow', kind);
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div className="w-[240px] flex-shrink-0 border-r border-border bg-card/50 backdrop-blur overflow-y-auto">
      <div className="p-4">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
          Adicionar nó
        </h2>
        <p className="text-[11px] text-muted-foreground mb-4 leading-relaxed">
          Arraste pro canvas e conecte os nós clicando nas bolinhas.
        </p>
        <div className="space-y-2">
          {PALETTE_ORDER.map((kind) => {
            const meta = NODE_META[kind];
            const Icon = meta.icon;
            return (
              <div
                key={kind}
                draggable
                onDragStart={(e) => onDragStart(e, kind)}
                className={cn(
                  'group flex items-center gap-2.5 rounded-lg border-2 bg-card p-2.5 cursor-grab active:cursor-grabbing transition-all',
                  'border-border hover:border-primary/50 hover:shadow-sm hover:-translate-y-0.5',
                )}
              >
                <div className={cn('w-8 h-8 rounded-md flex items-center justify-center flex-shrink-0', meta.colorClass)}>
                  <Icon className="w-4 h-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-[13px] font-medium text-foreground leading-tight">{meta.label}</div>
                  <div className="text-[11px] text-muted-foreground leading-tight">{meta.description}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
