// simulator-engine.ts
// Replica o motor Python (engine.py) em TS, sem I/O.
// Usado pelo simulador de fluxo do editor — sem WhatsApp, sem banco.

export type NodeKind =
  | 'trigger' | 'message' | 'buttons' | 'input' | 'condition'
  | 'tag' | 'move_stage' | 'handoff' | 'end' | 'delay' | 'http_request' | 'webhook_out';

export interface FlowNode {
  id: string;
  type?: string;
  data?: Record<string, any>;
  position?: { x: number; y: number };
}

export interface FlowEdge {
  id?: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
}

export interface Graph {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

export interface SimContact {
  name: string;
  wa_id: string;
}

export type BubbleKind = 'bot' | 'user' | 'system';

export interface ChatBubble {
  kind: BubbleKind;
  text: string;
  buttons?: Array<{ id: string; label: string }>;
  systemIcon?: string;
  ts: number;
}

export type WaitKind = null | 'buttons' | 'input' | 'end';

export interface SimState {
  bubbles: ChatBubble[];
  variables: Record<string, string>;
  currentNodeId: string | null;
  waitKind: WaitKind;
  finished: boolean;
  steps: number;
}

const MAX_STEPS = 100;

// ============================================================
// Helpers
// ============================================================
function nodeType(n: FlowNode): string {
  return n.type || (n.data as any)?.kind || '';
}

function findNode(graph: Graph, id: string | null | undefined): FlowNode | null {
  if (!id) return null;
  return graph.nodes.find((n) => String(n.id) === String(id)) || null;
}

function findNextNode(graph: Graph, sourceId: string, sourceHandle: string | null = null): FlowNode | null {
  if (sourceHandle !== null) {
    for (const e of graph.edges) {
      if (String(e.source) !== String(sourceId)) continue;
      if (e.sourceHandle !== sourceHandle) continue;
      return findNode(graph, e.target);
    }
    return null;
  }
  // sem handle: primeira edge SEM sourceHandle
  for (const e of graph.edges) {
    if (String(e.source) !== String(sourceId)) continue;
    if (e.sourceHandle) continue;
    return findNode(graph, e.target);
  }
  // fallback: primeira edge qualquer
  for (const e of graph.edges) {
    if (String(e.source) === String(sourceId)) return findNode(graph, e.target);
  }
  return null;
}

function findTriggerNode(graph: Graph, text: string): FlowNode | null {
  const tl = (text || '').trim().toLowerCase();
  let fallback: FlowNode | null = null;
  for (const n of graph.nodes) {
    if (nodeType(n) !== 'trigger') continue;
    const d = n.data || {};
    const mode = d.mode || 'any_message';
    if (mode === 'keyword') {
      const kw = ((d.keyword || '') as string).trim().toLowerCase();
      if (kw && tl.includes(kw)) return n;
    } else if (mode === 'any_message') {
      fallback = fallback || n;
    }
  }
  return fallback;
}

export function interpolate(
  tpl: string,
  vars: Record<string, string>,
  contact: SimContact,
): string {
  if (!tpl) return '';
  const merged: Record<string, string> = {
    nome: contact.name || '',
    telefone: contact.wa_id || '',
    ...vars,
  };
  let out = tpl;
  for (const [k, v] of Object.entries(merged)) {
    out = out.split('{' + k + '}').join(String(v));
  }
  return out;
}

export function validateInput(value: string, validation: string): boolean {
  const v = (value || '').trim();
  if (!validation || validation === 'text') return v.length > 0;
  if (validation === 'email') return /^[\w.\-+]+@[\w-]+\.[\w.\-]+$/.test(v);
  if (validation === 'cpf') return v.replace(/\D/g, '').length === 11;
  if (validation === 'phone') {
    const d = v.replace(/\D/g, '');
    return d.length >= 10 && d.length <= 13;
  }
  if (validation === 'number') {
    const cleaned = v.replace(/[^\d.,\-]/g, '').replace(/\./g, '').replace(',', '.');
    return !Number.isNaN(parseFloat(cleaned));
  }
  return true;
}

export function matchButtonChoice(
  buttons: Array<{ id: string; label: string }>,
  response: string,
): { id: string; label: string } | null {
  if (!buttons?.length || !response) return null;
  const clean = response.trim().toLowerCase();

  // número puro
  const digits = clean.replace(/\D/g, '');
  if (digits) {
    const idx = parseInt(digits, 10) - 1;
    if (idx >= 0 && idx < buttons.length) return buttons[idx];
  }
  // label (igual, contains)
  for (const b of buttons) {
    const l = (b.label || '').trim().toLowerCase();
    if (!l) continue;
    if (l === clean || l.includes(clean) || clean.includes(l)) return b;
  }
  // id
  for (const b of buttons) {
    if (b.id?.trim().toLowerCase() === clean) return b;
  }
  return null;
}

// ============================================================
// State initial
// ============================================================
export function initialState(): SimState {
  return {
    bubbles: [],
    variables: {},
    currentNodeId: null,
    waitKind: null,
    finished: false,
    steps: 0,
  };
}

// ============================================================
// Push helpers (imutáveis)
// ============================================================
function pushBubble(state: SimState, bubble: ChatBubble): SimState {
  return { ...state, bubbles: [...state.bubbles, bubble] };
}

function now() { return Date.now(); }

// ============================================================
// Execução de 1 nó
// Retorna: [novoState, próximoNó | null, esperar?]
// ============================================================
function executeNode(
  node: FlowNode,
  state: SimState,
  graph: Graph,
  contact: SimContact,
): [SimState, FlowNode | null, boolean] {
  const nt = nodeType(node);
  const data = node.data || {};
  let s = state;

  switch (nt) {
    case 'trigger':
      return [s, findNextNode(graph, node.id), false];

    case 'message': {
      const text = interpolate(data.text || '', s.variables, contact);
      if (text) s = pushBubble(s, { kind: 'bot', text, ts: now() });
      return [s, findNextNode(graph, node.id), false];
    }

    case 'buttons': {
      const text = interpolate(data.text || '', s.variables, contact);
      const buttons: Array<{ id: string; label: string }> = data.buttons || [];
      s = pushBubble(s, { kind: 'bot', text: text || 'Escolha uma opção:', buttons, ts: now() });
      s = { ...s, currentNodeId: node.id, waitKind: 'buttons' };
      return [s, null, true];
    }

    case 'input': {
      const prompt = interpolate(data.prompt || '', s.variables, contact);
      if (prompt) s = pushBubble(s, { kind: 'bot', text: prompt, ts: now() });
      s = { ...s, currentNodeId: node.id, waitKind: 'input' };
      return [s, null, true];
    }

    case 'condition': {
      const varName = data.variable || '';
      const op = data.operator || 'equals';
      const value = String(data.value ?? '');
      const actual = String(s.variables[varName] ?? '');
      const a = actual.trim().toLowerCase();
      const b = value.trim().toLowerCase();
      let result = false;
      if (op === 'equals') result = a === b;
      else if (op === 'not_equals') result = a !== b;
      else if (op === 'contains') result = a.includes(b);
      return [s, findNextNode(graph, node.id, result ? 'true' : 'false'), false];
    }

    case 'tag': {
      const name = (data.tag_name || '').trim();
      if (name) {
        s = pushBubble(s, {
          kind: 'system', text: `Tag adicionada: ${name}`,
          systemIcon: '🏷️', ts: now(),
        });
      }
      return [s, findNextNode(graph, node.id), false];
    }

    case 'move_stage': {
      const stage = (data.stage || '').trim();
      const pipelineId = data.pipeline_id;
      if (stage) {
        const suffix = pipelineId ? ` (pipeline #${pipelineId})` : '';
        s = pushBubble(s, {
          kind: 'system', text: `Movido para: ${stage}${suffix}`,
          systemIcon: '📊', ts: now(),
        });
      }
      return [s, findNextNode(graph, node.id), false];
    }

    case 'handoff': {
      const title = interpolate(data.task_title || 'Atendimento via workflow', s.variables, contact);
      const user = data.assigned_to_user_id ? `user #${data.assigned_to_user_id}` : 'sem responsável';
      s = pushBubble(s, {
        kind: 'system', text: `Tarefa criada: "${title}" → ${user}`,
        systemIcon: '👤', ts: now(),
      });
      const stage = (data.stage || '').trim();
      if (stage) {
        const pipelineId = data.pipeline_id;
        const suffix = pipelineId ? ` (pipeline #${pipelineId})` : '';
        s = pushBubble(s, {
          kind: 'system', text: `Movido para: ${stage}${suffix}`,
          systemIcon: '📊', ts: now(),
        });
      }
      s = pushBubble(s, {
        kind: 'system', text: 'Sessão encerrada — humano assume',
        systemIcon: '🤝', ts: now(),
      });
      s = { ...s, finished: true, waitKind: 'end', currentNodeId: node.id };
      return [s, null, false];
    }

    case 'delay': {
      const amount = Number(data.amount) || 1;
      const unit = data.unit || 'minutes';
      const label = unit === 'days' ? 'dia(s)' : unit === 'hours' ? 'hora(s)' : 'minuto(s)';
      s = pushBubble(s, {
        kind: 'system', text: `Delay de ${amount} ${label} (ignorado na simulação)`,
        systemIcon: '⏰', ts: now(),
      });
      return [s, findNextNode(graph, node.id), false];
    }

    case 'http_request': {
      const method = (data.method || 'GET').toUpperCase();
      const url = interpolate(data.url || '', s.variables, contact);
      s = pushBubble(s, {
        kind: 'system',
        text: `HTTP ${method} ${url || '(URL vazia)'} — simulado (segue branch "success")`,
        systemIcon: '🌐',
        ts: now(),
      });
      const prefix = (data.response_var_prefix || 'http').trim() || 'http';
      s = {
        ...s,
        variables: {
          ...s.variables,
          [`${prefix}_status`]: '200',
          [`${prefix}_ok`]: 'true',
          [`${prefix}_response_raw`]: '{"simulated":true}',
        },
      };
      return [s, findNextNode(graph, node.id, 'success'), false];
    }

    case 'webhook_out': {
      const url = interpolate(data.url || '', s.variables, contact);
      const ev = data.event_name || 'chatbot_event';
      s = pushBubble(s, {
        kind: 'system',
        text: `Webhook "${ev}" → ${url || '(URL vazia)'} — simulado (fire-and-forget)`,
        systemIcon: '📤',
        ts: now(),
      });
      return [s, findNextNode(graph, node.id), false];
    }

    case 'end':
      s = pushBubble(s, {
        kind: 'system', text: 'Fluxo encerrado',
        systemIcon: '🏁', ts: now(),
      });
      s = { ...s, finished: true, waitKind: 'end', currentNodeId: node.id };
      return [s, null, false];

    default:
      s = pushBubble(s, {
        kind: 'system', text: `Tipo de nó desconhecido: ${nt}`,
        systemIcon: '⚠️', ts: now(),
      });
      return [s, findNextNode(graph, node.id), false];
  }
}

function advanceFrom(
  state: SimState,
  startNode: FlowNode,
  graph: Graph,
  contact: SimContact,
): SimState {
  let s = state;
  let current: FlowNode | null = startNode;
  let steps = s.steps;

  while (current && steps < MAX_STEPS) {
    const [ns, nextNode, shouldWait] = executeNode(current, s, graph, contact);
    s = ns;
    steps++;
    if (shouldWait) {
      return { ...s, steps };
    }
    if (nextNode === null) {
      if (!s.finished) {
        s = pushBubble(s, {
          kind: 'system', text: 'Fim do fluxo (sem próximo nó)',
          systemIcon: '🏁', ts: now(),
        });
      }
      return { ...s, finished: true, waitKind: 'end', currentNodeId: current.id, steps };
    }
    current = nextNode;
  }

  if (steps >= MAX_STEPS) {
    s = pushBubble(s, {
      kind: 'system', text: `Limite de ${MAX_STEPS} passos atingido`,
      systemIcon: '⚠️', ts: now(),
    });
    return { ...s, finished: true, waitKind: 'end', steps };
  }

  return { ...s, steps };
}

// ============================================================
// Entry points públicos
// ============================================================
export function sendUserMessage(
  state: SimState,
  text: string,
  graph: Graph,
  contact: SimContact,
): SimState {
  if (state.finished) return state;
  let s = pushBubble(state, { kind: 'user', text, ts: now() });

  // Sem conversa ainda → procurar trigger
  if (!s.currentNodeId || s.waitKind === null) {
    const trigger = findTriggerNode(graph, text);
    if (!trigger) {
      return pushBubble(s, {
        kind: 'system',
        text: 'Nenhum gatilho bateu com essa mensagem',
        systemIcon: '🚫',
        ts: now(),
      });
    }
    return advanceFrom(s, trigger, graph, contact);
  }

  const waiting = findNode(graph, s.currentNodeId);
  if (!waiting) {
    return pushBubble(s, {
      kind: 'system',
      text: 'Nó atual não existe no grafo',
      systemIcon: '⚠️',
      ts: now(),
    });
  }

  const nt = nodeType(waiting);

  if (nt === 'buttons') {
    const buttons = (waiting.data?.buttons || []) as Array<{ id: string; label: string }>;
    const selected = matchButtonChoice(buttons, text);
    if (!selected) {
      return pushBubble(s, {
        kind: 'bot',
        text: 'Não entendi. Escolha uma das opções:',
        buttons,
        ts: now(),
      });
    }
    const captureTo = waiting.data?.capture_to;
    if (captureTo) {
      s = { ...s, variables: { ...s.variables, [captureTo]: selected.label || selected.id } };
    }
    const next = findNextNode(graph, waiting.id, selected.id);
    if (!next) return { ...s, finished: true, waitKind: 'end' };
    return advanceFrom(s, next, graph, contact);
  }

  if (nt === 'input') {
    const d = waiting.data || {};
    const validation = d.validation || 'text';
    if (!validateInput(text, validation)) {
      const err = d.error_message || 'Resposta inválida. Tente novamente.';
      return pushBubble(s, { kind: 'bot', text: err, ts: now() });
    }
    const varName = d.variable || 'resposta';
    s = { ...s, variables: { ...s.variables, [varName]: text.trim() } };
    const next = findNextNode(graph, waiting.id);
    if (!next) return { ...s, finished: true, waitKind: 'end' };
    return advanceFrom(s, next, graph, contact);
  }

  // outro tipo parado → só tenta avançar
  const next = findNextNode(graph, waiting.id);
  if (!next) return { ...s, finished: true, waitKind: 'end' };
  return advanceFrom(s, next, graph, contact);
}

export function clickButton(
  state: SimState,
  button: { id: string; label: string },
  graph: Graph,
  contact: SimContact,
): SimState {
  return sendUserMessage(state, button.label, graph, contact);
}
