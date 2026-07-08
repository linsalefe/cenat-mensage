import type { Edge, Node } from "@xyflow/react";

export type FlowKind = "chatbot" | "broadcast";

export interface ValidationError {
  nodeId?: string;
  message: string;
}

export interface GraphInput {
  kind: FlowKind;
  nodes: Node[];
  edges: Edge[];
}

export function validateFlow(graph: GraphInput): ValidationError[] {
  if (graph.kind === "broadcast") return validateBroadcastFlow(graph);
  return validateChatbotFlow(graph);
}

function validateChatbotFlow(g: { nodes: Node[]; edges: Edge[] }): ValidationError[] {
  const errs: ValidationError[] = [];
  const triggers = g.nodes.filter((n) => n.type === "trigger");
  if (triggers.length === 0) {
    errs.push({ message: "Adicione um nó de gatilho (trigger)" });
  }
  if (triggers.length > 1) {
    errs.push({ message: "O fluxo pode ter apenas um gatilho" });
  }
  if (g.nodes.length < 2) {
    errs.push({ message: "Conecte pelo menos mais um nó após o gatilho" });
  }
  // Nós órfãos (sem entrada, exceto trigger)
  const targetIds = new Set(g.edges.map((e) => e.target));
  g.nodes.forEach((n) => {
    if (n.type !== "trigger" && !targetIds.has(n.id)) {
      const label =
        (n.data as { label?: string } | undefined)?.label || n.type || "sem tipo";
      errs.push({
        nodeId: n.id,
        message: `Nó "${label}" está desconectado`,
      });
    }
  });
  return errs;
}

function validateBroadcastFlow(g: { nodes: Node[]; edges: Edge[] }): ValidationError[] {
  const errs: ValidationError[] = [];
  const byType = (t: string) => g.nodes.filter((n) => n.type === t);

  const trigger = byType("trigger_schedule");
  const audience = byType("audience");
  const messages = byType("message_media");
  const templates = byType("template_send");
  const send = byType("broadcast_send");

  if (trigger.length === 0) {
    errs.push({ message: "Adicione um nó de agendamento (trigger_schedule)" });
  }
  if (trigger.length > 1) {
    errs.push({ message: "O fluxo pode ter apenas um nó de agendamento" });
  }

  if (audience.length === 0) {
    errs.push({ message: "Adicione um nó de audiência" });
  }
  if (audience.length > 1) {
    errs.push({ message: "O fluxo pode ter apenas um nó de audiência" });
  }

  if (messages.length + templates.length < 1) {
    errs.push({ message: "Adicione pelo menos uma mensagem (texto/mídia ou template)" });
  }

  if (templates.length > 1) {
    errs.push({ message: "O fluxo pode ter apenas um nó de template" });
  }

  if (send.length === 0) {
    errs.push({ message: "Adicione o nó de disparo (broadcast_send) ao final" });
  }
  if (send.length > 1) {
    errs.push({ message: "O fluxo pode ter apenas um nó de disparo" });
  }

  // Audiência precisa ter channel_id
  audience.forEach((n) => {
    const data = (n.data || {}) as { channel_id?: number | null };
    if (!data.channel_id) {
      errs.push({ nodeId: n.id, message: "Selecione um canal no nó de audiência" });
    }
  });

  // Mensagens precisam ter texto OU mídia
  messages.forEach((n) => {
    const data = (n.data || {}) as {
      text?: string;
      media_id?: number | null;
      label?: string;
    };
    const hasText = !!data.text && data.text.trim() !== "";
    const hasMedia = !!data.media_id;
    if (!hasText && !hasMedia) {
      const label = data.label || "mensagem";
      errs.push({
        nodeId: n.id,
        message: `Nó "${label}" precisa de texto ou mídia`,
      });
    }
  });

  // Template precisa estar selecionado, sincronizado e com todos os valores preenchidos
  templates.forEach((n) => {
    const data = (n.data || {}) as {
      template_id?: number | null;
      template_params?: Array<{ type?: string; value?: string }>;
      template_param_count?: number;
    };
    if (!data.template_id) {
      errs.push({ nodeId: n.id, message: "Selecione um template no nó de template" });
      return;
    }
    const params = Array.isArray(data.template_params) ? data.template_params : [];
    // Nó legado (sem contagem registrada) → força reabrir p/ sincronizar com o template
    if (typeof data.template_param_count !== "number") {
      errs.push({
        nodeId: n.id,
        message: "Reabra o nó Template para configurar os parâmetros",
      });
      return;
    }
    // Parâmetros faltando (grafo salvo antes da sincronização)
    if (params.length < data.template_param_count) {
      errs.push({
        nodeId: n.id,
        message: "Configure os parâmetros do template (reabra o nó Template)",
      });
      return;
    }
    // Cada parâmetro de valor precisa estar preenchido
    params.forEach((p, i) => {
      const needsValue = p?.type === "fixed_text" || p?.type === "custom_var";
      if (needsValue && (!p.value || String(p.value).trim() === "")) {
        errs.push({
          nodeId: n.id,
          message: `Preencha o parâmetro {{${i + 1}}} do template`,
        });
      }
    });
  });

  return errs;
}

/**
 * Formata os erros como texto legível — quando o erro tem nodeId, concatena
 * "(nó: <label-ou-tipo>)" usando o grafo original pra resolver label.
 */
export function describeErrors(
  errors: ValidationError[],
  nodes: Node[],
): string[] {
  return errors.map((err) => {
    if (!err.nodeId) return err.message;
    const n = nodes.find((x) => x.id === err.nodeId);
    if (!n) return err.message;
    const data = (n.data || {}) as { label?: string };
    const ref = data.label || n.type || err.nodeId;
    return `${err.message} (nó: ${ref})`;
  });
}
