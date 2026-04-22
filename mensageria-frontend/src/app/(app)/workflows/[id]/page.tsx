'use client';

import {
  useEffect, useState, useCallback, useRef, useMemo,
} from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ReactFlow, ReactFlowProvider, Background, Controls, MiniMap,
  useNodesState, useEdgesState, addEdge, useReactFlow,
  type Node, type Edge, type Connection, type NodeChange, type EdgeChange,
  type OnNodesChange, type OnEdgesChange,
  BackgroundVariant, MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  ArrowLeft, Loader2, CheckCircle2, CircleAlert, Rocket, Pause,
  Radio, Sparkles, Workflow, AlertTriangle, CheckCircle, LayoutGrid, Play,
} from 'lucide-react';
import { SimulatorDrawer } from '@/components/chatbot/simulator-drawer';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useAuth } from '@/contexts/auth-context';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  nodeTypes, createDefaultNodeData, type NodeKind, NodePalette,
} from '@/components/chatbot/node-catalog';
import { edgeTypes } from '@/components/chatbot/edge-components';
import {
  NodeInspector, type KanbanCol, type UserOpt, type PipelineOpt,
} from '@/components/chatbot/node-inspector';

interface Flow {
  id: number;
  name: string;
  description: string | null;
  graph: { nodes: Node[]; edges: Edge[] };
  published_graph: { nodes: Node[]; edges: Edge[] } | null;
  is_published: boolean;
  version: number;
}

interface ChannelStatus {
  channel_id: number;
  channel_name: string;
  channel_type: string;
  current_mode: 'ai' | 'chatbot' | 'none';
  current_flow_id: number | null;
  current_flow_name: string | null;
  status: 'free' | 'ai_conflict' | 'other_chatbot' | 'same_chatbot';
}

const AUTOSAVE_DELAY_MS = 1500;

function EditorInner({ flowId }: { flowId: number }) {
  const router = useRouter();
  const { screenToFlowPosition } = useReactFlow();

  const [flow, setFlow] = useState<Flow | null>(null);
  const [loading, setLoading] = useState(true);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [nameDraft, setNameDraft] = useState('');
  const [isDirty, setIsDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [publishing, setPublishing] = useState(false);

  // Publish-to-Channel
  const [publishDialogOpen, setPublishDialogOpen] = useState(false);
  const [channelStatuses, setChannelStatuses] = useState<ChannelStatus[]>([]);
  const [loadingChannels, setLoadingChannels] = useState(false);
  const [selectedChannelId, setSelectedChannelId] = useState<number | null>(null);
  const [activeChannel, setActiveChannel] = useState<ChannelStatus | null>(null);

  const [simulatorOpen, setSimulatorOpen] = useState(false);

  // Detecta se há alterações não publicadas (graph atual != published_graph)
  const hasUnpublishedChanges = useMemo(() => {
    if (!flow?.is_published) return false;
    if (!flow?.published_graph) return true;
    const canonize = (g: any) =>
      JSON.stringify({
        nodes: (g?.nodes || []).map((n: any) => ({
          id: n.id, type: n.type, data: n.data, position: n.position,
        })),
        edges: (g?.edges || []).map((e: any) => ({
          source: e.source, target: e.target,
          sourceHandle: e.sourceHandle ?? null,
          targetHandle: e.targetHandle ?? null,
        })),
      });
    return canonize({ nodes, edges }) !== canonize(flow.published_graph);
  }, [flow?.is_published, flow?.published_graph, nodes, edges]);

  const [kanbanColumns, setKanbanColumns] = useState<KanbanCol[]>([]);
  const [users, setUsers] = useState<UserOpt[]>([]);
  const [pipelines, setPipelines] = useState<PipelineOpt[]>([]);

  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const bootstrapping = useRef(true);

  // ── Load ──────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const [flowRes, kbRes, usersRes, pipelinesRes] = await Promise.all([
          api.get(`/chatbot/flows/${flowId}`),
          api.get('/tenant/kanban-columns').catch(() => ({ data: [] })),
          api.get('/users/list').catch(() => ({ data: [] })),
          api.get('/pipelines').catch(() => ({ data: [] })),
        ]);

        const f: Flow = flowRes.data;
        const graph = f.graph || { nodes: [], edges: [] };

        let initialNodes: Node[] = Array.isArray(graph.nodes) ? graph.nodes : [];
        const initialEdges: Edge[] = Array.isArray(graph.edges) ? graph.edges : [];

        if (initialNodes.length === 0) {
          initialNodes = [{
            id: `trigger_${Date.now()}`,
            type: 'trigger',
            position: { x: 120, y: 220 },
            data: createDefaultNodeData('trigger'),
          }];
        }

        setFlow(f);
        setNameDraft(f.name);
        setNodes(initialNodes);
        setEdges(initialEdges);
        setKanbanColumns(Array.isArray(kbRes.data) ? kbRes.data : []);
        setUsers(Array.isArray(usersRes.data) ? usersRes.data : []);
        setPipelines(Array.isArray(pipelinesRes.data) ? pipelinesRes.data : []);

        // Identifica canal ativo atual (pra badge no top bar)
        try {
          const stsRes = await api.get(`/chatbot/flows/${flowId}/channels-status`);
          const statuses: ChannelStatus[] = stsRes.data || [];
          const active = statuses.find((s) => s.status === 'same_chatbot') || null;
          setActiveChannel(active);
        } catch {
          // silencioso — não bloqueia o editor
        }
      } catch (err: unknown) {
        const e = err as { response?: { status?: number } };
        if (e.response?.status === 404) {
          toast.error('Workflow não encontrado');
          router.push('/workflows');
        } else {
          toast.error('Erro ao carregar workflow');
          router.push('/workflows');
        }
      } finally {
        setLoading(false);
        setTimeout(() => { bootstrapping.current = false; }, 100);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flowId]);

  // ── Dirty tracking ────────────────────────────────────
  const handleNodesChange: OnNodesChange = useCallback((changes: NodeChange[]) => {
    onNodesChange(changes);
    if (bootstrapping.current) return;
    const significant = changes.some((c) =>
      c.type === 'add' || c.type === 'remove' ||
      (c.type === 'position' && !c.dragging) ||
      c.type === 'replace'
    );
    if (significant) setIsDirty(true);
  }, [onNodesChange]);

  const handleEdgesChange: OnEdgesChange = useCallback((changes: EdgeChange[]) => {
    onEdgesChange(changes);
    if (bootstrapping.current) return;
    setIsDirty(true);
  }, [onEdgesChange]);

  const onConnect = useCallback((params: Connection) => {
    setEdges((eds) => addEdge({
      ...params,
      type: 'custom',
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
    }, eds));
    setIsDirty(true);
  }, [setEdges]);

  // ── Drag-and-drop ─────────────────────────────────────
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    const kind = event.dataTransfer.getData('application/reactflow') as NodeKind;
    if (!kind) return;

    const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    const newNode: Node = {
      id: `${kind}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      type: kind,
      position,
      data: createDefaultNodeData(kind),
    };
    setNodes((nds) => nds.concat(newNode));
    setIsDirty(true);
    setSelectedId(newNode.id);
  }, [screenToFlowPosition, setNodes]);

  // ── Selection ─────────────────────────────────────────
  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => setSelectedId(node.id), []);
  const onPaneClick = useCallback(() => setSelectedId(null), []);

  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selectedId) || null,
    [nodes, selectedId],
  );

  // ── Inspector updates ─────────────────────────────────
  const updateSelectedNodeData = useCallback((newData: Record<string, any>) => {
    if (!selectedId) return;
    const clean = { ...newData };
    if (clean.stage === '__none__') clean.stage = '';

    setNodes((nds) =>
      nds.map((n) => (n.id === selectedId ? { ...n, data: { ...clean } } : n)),
    );
    if (selectedNode?.type === 'buttons' && Array.isArray(clean.buttons)) {
      const validIds = new Set<string>((clean.buttons as any[]).map((b: any) => b.id));
      setEdges((eds) =>
        eds.filter((e) => e.source !== selectedId || !e.sourceHandle || validIds.has(e.sourceHandle)),
      );
    }
    setIsDirty(true);
  }, [selectedId, selectedNode, setNodes, setEdges]);

  const deleteSelectedNode = useCallback(() => {
    if (!selectedId) return;
    setNodes((nds) => nds.filter((n) => n.id !== selectedId));
    setEdges((eds) => eds.filter((e) => e.source !== selectedId && e.target !== selectedId));
    setSelectedId(null);
    setIsDirty(true);
  }, [selectedId, setNodes, setEdges]);

  // ── Auto-save ─────────────────────────────────────────
  const saveDraft = useCallback(async (showToast = false) => {
    if (!flow || saving) return;
    setSaving(true);
    try {
      const payload: any = { graph: { nodes, edges } };
      if (nameDraft.trim() && nameDraft.trim() !== flow.name) payload.name = nameDraft.trim();
      await api.put(`/chatbot/flows/${flow.id}`, payload);
      setIsDirty(false);
      setLastSaved(new Date());
      if (showToast) toast.success('Salvo');
      if (payload.name) setFlow((f) => (f ? { ...f, name: payload.name } : f));
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e.response?.data?.detail || 'Erro ao salvar');
    } finally {
      setSaving(false);
    }
  }, [flow, nodes, edges, nameDraft, saving]);

  useEffect(() => {
    if (bootstrapping.current || !isDirty) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => { saveDraft(); }, AUTOSAVE_DELAY_MS);
    return () => { if (saveTimer.current) clearTimeout(saveTimer.current); };
  }, [nodes, edges, nameDraft, isDirty, saveDraft]);

  // ── beforeunload ──────────────────────────────────────
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (isDirty || hasUnpublishedChanges) { e.preventDefault(); }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty, hasUnpublishedChanges]);

  // ── Auto-layout horizontal ─────────────────────────────
  const autoLayout = useCallback(() => {
    const COL_WIDTH = 320;
    const ROW_HEIGHT = 180;
    const LEFT = 100;
    const TOP = 100;

    const nodeIds = new Set(nodes.map((n) => n.id));
    const triggers = nodes.filter((n) => n.type === 'trigger').map((n) => n.id);
    const starts = triggers.length ? triggers : [nodes[0]?.id].filter(Boolean);

    const level: Record<string, number> = {};
    starts.forEach((id) => { level[id] = 0; });

    const queue = [...starts];
    while (queue.length) {
      const cur = queue.shift()!;
      const outgoing = edges.filter((e) => e.source === cur);
      for (const e of outgoing) {
        if (!nodeIds.has(e.target)) continue;
        const next = (level[cur] ?? 0) + 1;
        if (level[e.target] === undefined || level[e.target] < next) {
          level[e.target] = next;
          queue.push(e.target);
        }
      }
    }

    // Nodes not reached by BFS get level 0
    nodes.forEach((n) => { if (level[n.id] === undefined) level[n.id] = 0; });

    const groups: Record<number, string[]> = {};
    nodes.forEach((n) => {
      const lv = level[n.id] ?? 0;
      (groups[lv] = groups[lv] || []).push(n.id);
    });

    setNodes((nds) =>
      nds.map((n) => {
        const lv = level[n.id] ?? 0;
        const column = groups[lv] || [];
        const idx = column.indexOf(n.id);
        return {
          ...n,
          position: {
            x: LEFT + lv * COL_WIDTH,
            y: TOP + idx * ROW_HEIGHT,
          },
        };
      }),
    );
    setIsDirty(true);
    toast.success('Fluxo reorganizado');
  }, [nodes, edges, setNodes]);

  // ── Publicar: abre diálogo de seleção de canal ──────────
  const openPublishDialog = async () => {
    if (!flow) return;
    setPublishDialogOpen(true);
    setSelectedChannelId(null);
    setLoadingChannels(true);
    try {
      const res = await api.get(`/chatbot/flows/${flow.id}/channels-status`);
      const statuses: ChannelStatus[] = res.data || [];
      setChannelStatuses(statuses);
      // Pré-seleciona se já houver canal com este fluxo
      const same = statuses.find((s) => s.status === 'same_chatbot');
      if (same) setSelectedChannelId(same.channel_id);
    } catch {
      toast.error('Erro ao carregar canais');
    } finally {
      setLoadingChannels(false);
    }
  };

  const confirmPublish = async () => {
    if (!flow || !selectedChannelId) return;
    const chosen = channelStatuses.find((c) => c.channel_id === selectedChannelId);
    if (!chosen) return;

    // Confirmação extra pra casos de conflito
    if (chosen.status === 'ai_conflict') {
      const ok = confirm(
        `O canal "${chosen.channel_name}" está com o Agente de IA ativo. `
        + `Publicar o workflow aqui vai DESATIVAR a IA neste canal. Continuar?`
      );
      if (!ok) return;
    } else if (chosen.status === 'other_chatbot') {
      const ok = confirm(
        `O canal "${chosen.channel_name}" já tem o workflow `
        + `"${chosen.current_flow_name}" rodando. `
        + `Publicar aqui vai SUBSTITUIR o fluxo anterior. Continuar?`
      );
      if (!ok) return;
    }

    setPublishing(true);
    try {
      // 1. Salvar rascunho
      if (saveTimer.current) clearTimeout(saveTimer.current);
      await saveDraft();
      // 2. Publicar o fluxo (valida trigger)
      await api.post(`/chatbot/flows/${flow.id}/publish`);
      // 3. Ativar no canal escolhido (force=true substitui o que estiver lá)
      await api.put(`/chatbot/channels/${selectedChannelId}/mode`, {
        operation_mode: 'chatbot',
        active_chatbot_flow_id: flow.id,
        force: true,
      });
      setFlow((f) => (f ? {
        ...f,
        is_published: true,
        version: f.version + 1,
        published_graph: { nodes, edges },
      } : f));
      setActiveChannel({
        ...chosen,
        current_mode: 'chatbot',
        current_flow_id: flow.id,
        current_flow_name: flow.name,
        status: 'same_chatbot',
      });
      setPublishDialogOpen(false);
      toast.success(`Workflow publicado em "${chosen.channel_name}"!`);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e.response?.data?.detail || 'Erro ao publicar');
    } finally {
      setPublishing(false);
    }
  };

  const handleUnpublish = async () => {
    if (!flow) return;
    setPublishing(true);
    try {
      await api.post(`/chatbot/flows/${flow.id}/unpublish`);
      setFlow((f) => (f ? { ...f, is_published: false } : f));
      toast.success('Workflow despublicado');
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e.response?.data?.detail || 'Erro ao despublicar');
    } finally {
      setPublishing(false);
    }
  };

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-background overflow-hidden">
      {/* Top bar */}
      <header className="flex-shrink-0 flex items-center justify-between gap-4 px-4 py-3 border-b border-border bg-card">
        <div className="flex items-center gap-3 min-w-0">
          <Button variant="ghost" size="icon" onClick={() => router.push('/workflows')} className="h-9 w-9">
            <ArrowLeft className="w-4 h-4" />
          </Button>
          <Input
            value={nameDraft}
            onChange={(e) => { setNameDraft(e.target.value); setIsDirty(true); }}
            className="h-9 font-medium text-[15px] max-w-[320px] border-transparent hover:border-border focus:border-border"
            placeholder="Nome do workflow"
          />
          <SaveStatus saving={saving} dirty={isDirty} lastSaved={lastSaved} />
          <Button
            variant="ghost"
            size="sm"
            onClick={autoLayout}
            className="h-8 gap-1.5 text-muted-foreground hover:text-foreground"
            title="Organiza os nós em layout horizontal"
          >
            <LayoutGrid className="w-3.5 h-3.5" />
            Reorganizar
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setSimulatorOpen(true)}
            className="h-8 gap-1.5 border-primary/30 text-primary hover:bg-primary hover:text-primary-foreground"
            title="Testar o fluxo sem enviar WhatsApp"
          >
            <Play className="w-3.5 h-3.5" />
            Testar
          </Button>
        </div>
        <div className="flex items-center gap-2">
          {flow?.is_published ? (
            <>
              <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400 px-2 py-1 rounded-full bg-emerald-500/10">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Publicado &middot; v{flow.version}
              </span>
              {hasUnpublishedChanges && (
                <span
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-300 px-2 py-1 rounded-full bg-amber-500/15 border border-amber-500/30"
                  title="Suas alterações estão salvas, mas o bot continua rodando a versão publicada. Clique em Publicar para aplicar."
                >
                  <CircleAlert className="w-3 h-3" />
                  Alterações não publicadas
                </span>
              )}
              {activeChannel ? (
                <span className="hidden md:inline-flex items-center gap-1.5 text-xs font-medium text-foreground px-2 py-1 rounded-full bg-muted">
                  <Radio className="w-3 h-3 text-primary" />
                  {activeChannel.channel_name}
                </span>
              ) : (
                <span className="hidden md:inline-flex items-center gap-1.5 text-xs font-medium text-amber-600 dark:text-amber-400 px-2 py-1 rounded-full bg-amber-500/10">
                  <AlertTriangle className="w-3 h-3" />
                  Não ativado em nenhum canal
                </span>
              )}
              <Button variant="outline" size="sm" onClick={openPublishDialog} disabled={publishing}>
                Trocar canal
              </Button>
              <Button variant="outline" size="sm" onClick={handleUnpublish} disabled={publishing}>
                {publishing ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Pause className="w-4 h-4 mr-1" /> Despublicar</>}
              </Button>
            </>
          ) : (
            <Button size="sm" onClick={openPublishDialog} disabled={publishing} className="gap-1.5">
              {publishing ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Rocket className="w-4 h-4" /> Publicar</>}
            </Button>
          )}
        </div>
      </header>

      {/* Mobile guard */}
      <div className="lg:hidden flex-1 flex items-center justify-center p-8 text-center">
        <div className="max-w-sm">
          <div className="text-5xl mb-4">🖥</div>
          <h3 className="text-lg font-semibold mb-2">Abra em um computador</h3>
          <p className="text-sm text-muted-foreground">
            O editor de workflow precisa de uma tela maior pra você desenhar os fluxos com conforto.
          </p>
        </div>
      </div>

      {/* Workspace (desktop) */}
      <div className="hidden lg:flex flex-1 min-h-0 overflow-hidden">
        <NodePalette />

        <div className="flex-1 min-w-0 relative" ref={reactFlowWrapper} onDrop={onDrop} onDragOver={onDragOver}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            fitView
            fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
            defaultEdgeOptions={{
              type: 'custom',
              animated: true,
              markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
            }}
            proOptions={{ hideAttribution: true }}
            deleteKeyCode={['Backspace', 'Delete']}
            connectionLineStyle={{ strokeWidth: 2, stroke: '#6366f1' }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
            <Controls position="bottom-left" showInteractive={false} />
            <MiniMap
              position="bottom-right"
              nodeStrokeWidth={3}
              pannable
              zoomable
              style={{ background: 'var(--card)' }}
            />
          </ReactFlow>
        </div>

        {selectedNode && (
          <NodeInspector
            node={selectedNode}
            onChange={updateSelectedNodeData}
            onDelete={deleteSelectedNode}
            kanbanColumns={kanbanColumns}
            users={users}
            pipelines={pipelines}
          />
        )}
      </div>

      <SimulatorDrawer
        open={simulatorOpen}
        onClose={() => setSimulatorOpen(false)}
        graph={{ nodes, edges }}
      />

      {/* Dialog: publicar em qual canal */}
      <Dialog open={publishDialogOpen} onOpenChange={setPublishDialogOpen}>
        <DialogContent className="sm:max-w-[520px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Rocket className="w-5 h-5 text-primary" />
              Publicar workflow em qual canal?
            </DialogTitle>
            <DialogDescription>
              Escolha o canal onde este workflow vai responder automaticamente.
              Um workflow fica ativo em apenas um canal por vez.
            </DialogDescription>
          </DialogHeader>

          {loadingChannels ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-primary" />
            </div>
          ) : channelStatuses.length === 0 ? (
            <div className="text-center py-8 px-4">
              <Radio className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">
                Nenhum canal encontrado. Crie um canal em <strong>/canais</strong> primeiro.
              </p>
            </div>
          ) : (
            <div className="space-y-2 max-h-[380px] overflow-y-auto py-2">
              {channelStatuses.map((ch) => (
                <ChannelRadioCard
                  key={ch.channel_id}
                  channel={ch}
                  selected={selectedChannelId === ch.channel_id}
                  onSelect={() => setSelectedChannelId(ch.channel_id)}
                />
              ))}
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setPublishDialogOpen(false)} disabled={publishing}>
              Cancelar
            </Button>
            <Button
              onClick={confirmPublish}
              disabled={publishing || !selectedChannelId}
              className="gap-1.5"
            >
              {publishing ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Rocket className="w-4 h-4" /> Publicar aqui</>}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SaveStatus({ saving, dirty, lastSaved }: { saving: boolean; dirty: boolean; lastSaved: Date | null }) {
  if (saving) return <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><Loader2 className="w-3.5 h-3.5 animate-spin" /> Salvando...</span>;
  if (dirty) return <span className="inline-flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400"><CircleAlert className="w-3.5 h-3.5" /> Não salvo</span>;
  if (lastSaved) return <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> Salvo</span>;
  return null;
}

// ============================================================
// Card de canal no diálogo de publicar
// ============================================================
function ChannelRadioCard({
  channel, selected, onSelect,
}: {
  channel: ChannelStatus;
  selected: boolean;
  onSelect: () => void;
}) {
  const statusBadge = {
    free: {
      label: 'Livre',
      classes: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20',
      icon: CheckCircle,
    },
    ai_conflict: {
      label: 'Agente de IA ativo',
      classes: 'bg-violet-500/10 text-violet-700 dark:text-violet-400 border-violet-500/20',
      icon: Sparkles,
    },
    other_chatbot: {
      label: `Workflow: ${channel.current_flow_name || 'outro'}`,
      classes: 'bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-500/20',
      icon: Workflow,
    },
    same_chatbot: {
      label: 'Este workflow já está ativo',
      classes: 'bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/20',
      icon: CheckCircle2,
    },
  }[channel.status];

  const StatusIcon = statusBadge.icon;

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'w-full text-left rounded-lg border-2 p-3 transition-all flex items-start gap-3',
        selected
          ? 'border-primary bg-primary/5 shadow-sm'
          : 'border-border hover:border-primary/40 hover:bg-muted/30',
      )}
    >
      <div className={cn(
        'w-4 h-4 rounded-full border-2 mt-0.5 flex-shrink-0 flex items-center justify-center',
        selected ? 'border-primary' : 'border-muted-foreground/40',
      )}>
        {selected && <div className="w-2 h-2 rounded-full bg-primary" />}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <Radio className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
          <span className="font-medium text-sm text-foreground truncate">{channel.channel_name}</span>
          <span className="text-[10px] uppercase text-muted-foreground font-semibold">
            {channel.channel_type}
          </span>
        </div>
        <div className={cn(
          'inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border',
          statusBadge.classes,
        )}>
          <StatusIcon className="w-3 h-3" />
          {statusBadge.label}
        </div>
        {channel.status === 'ai_conflict' && (
          <p className="text-[11px] text-muted-foreground mt-1.5">
            Publicar aqui vai <strong>desativar o Agente de IA</strong> neste canal.
          </p>
        )}
        {channel.status === 'other_chatbot' && (
          <p className="text-[11px] text-muted-foreground mt-1.5">
            Publicar aqui vai <strong>substituir o workflow atual</strong>.
          </p>
        )}
      </div>
    </button>
  );
}


// ============================================================
// Default export — wrap in provider
// ============================================================
export default function ChatbotEditorPage() {
  const params = useParams();
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();

  const rawId = params?.id;
  const flowId = useMemo(() => {
    const s = Array.isArray(rawId) ? rawId[0] : rawId;
    const n = s ? parseInt(s, 10) : NaN;
    return Number.isFinite(n) ? n : null;
  }, [rawId]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.push('/login'); return; }
  }, [authLoading, user, router]);

  if (authLoading || !flowId) {
    return <div className="h-screen flex items-center justify-center bg-background"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;
  }

  return (
    <ReactFlowProvider>
      <EditorInner flowId={flowId} />
    </ReactFlowProvider>
  );
}
