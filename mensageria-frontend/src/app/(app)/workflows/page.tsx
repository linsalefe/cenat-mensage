'use client';

import { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Plus, Workflow, MoreVertical, Copy, Pencil, Trash2,
  Play, Pause, Search, Loader2, MessageSquareText, Sparkles,
  CheckCircle2, FileEdit, Users,
} from 'lucide-react';
import { SessionsDrawer } from '@/components/chatbot/sessions-drawer';
import { useAuth } from '@/contexts/auth-context';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

interface Flow {
  id: number;
  name: string;
  description: string | null;
  is_published: boolean;
  version: number;
  kind?: 'chatbot' | 'broadcast';
  created_at: string;
  updated_at: string;
}

function ChatbotListContent() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();

  const [flows, setFlows] = useState<Flow[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [creating, setCreating] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<Flow | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [sessionsTarget, setSessionsTarget] = useState<Flow | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.push('/login');
      return;
    }
    loadFlows();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user]);

  const loadFlows = async () => {
    setLoading(true);
    try {
      const res = await api.get('/chatbot/flows');
      setFlows(res.data || []);
    } catch (err: unknown) {
      const e = err as { response?: { status?: number; data?: { detail?: string } } };
      toast.error('Erro ao carregar workflows');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    const trimmed = newName.trim();
    if (!trimmed) {
      toast.error('Dê um nome ao workflow');
      return;
    }
    setCreating(true);
    try {
      const res = await api.post('/chatbot/flows', {
        name: trimmed,
        description: newDesc.trim() || null,
      });
      toast.success('Workflow criado');
      setCreateOpen(false);
      setNewName('');
      setNewDesc('');
      router.push(`/workflows/${res.data.id}`);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e.response?.data?.detail || 'Erro ao criar workflow');
    } finally {
      setCreating(false);
    }
  };

  const handleDuplicate = async (flow: Flow) => {
    try {
      await api.post(`/chatbot/flows/${flow.id}/duplicate`);
      toast.success('Workflow duplicado');
      loadFlows();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e.response?.data?.detail || 'Erro ao duplicar');
    }
  };

  const handleTogglePublish = async (flow: Flow) => {
    const endpoint = flow.is_published ? 'unpublish' : 'publish';
    try {
      await api.post(`/chatbot/flows/${flow.id}/${endpoint}`);
      toast.success(flow.is_published ? 'Workflow despublicado' : 'Workflow publicado');
      loadFlows();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e.response?.data?.detail || 'Erro ao atualizar');
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/chatbot/flows/${deleteTarget.id}`);
      toast.success('Workflow excluído');
      setDeleteTarget(null);
      loadFlows();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e.response?.data?.detail || 'Erro ao excluir');
    } finally {
      setDeleting(false);
    }
  };

  const filteredFlows = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return flows;
    return flows.filter(
      (f) =>
        f.name.toLowerCase().includes(q) ||
        (f.description || '').toLowerCase().includes(q),
    );
  }, [flows, search]);

  const stats = useMemo(
    () => ({
      total: flows.length,
      published: flows.filter((f) => f.is_published).length,
      drafts: flows.filter((f) => !f.is_published).length,
    }),
    [flows],
  );

  const formatRelative = (iso: string) => {
    try {
      const date = new Date(iso);
      const diff = Date.now() - date.getTime();
      const mins = Math.floor(diff / 60000);
      if (mins < 1) return 'agora';
      if (mins < 60) return `há ${mins} min`;
      const hours = Math.floor(mins / 60);
      if (hours < 24) return `há ${hours}h`;
      const days = Math.floor(hours / 24);
      if (days < 30) return `há ${days}d`;
      return date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' });
    } catch {
      return '—';
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto pb-12 space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4"
      >
        <div>
          <p className="text-sm text-muted-foreground mb-0.5">Automação sem código</p>
          <h1 className="text-2xl font-semibold text-foreground tracking-tight flex items-center gap-2">
            <Workflow className="w-6 h-6 text-primary" />
            Workflows
          </h1>
        </div>
        <Button onClick={() => setCreateOpen(true)} size="lg" className="gap-2 shadow-sm">
          <Plus className="w-4 h-4" />
          Novo workflow
        </Button>
      </motion.div>

      {/* Stats */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, delay: 0.05 }}
        className="grid grid-cols-1 sm:grid-cols-3 gap-3"
      >
        <StatCard icon={<Workflow className="w-4 h-4" />} label="Total" value={stats.total} tone="neutral" />
        <StatCard icon={<CheckCircle2 className="w-4 h-4" />} label="Publicados" value={stats.published} tone="success" />
        <StatCard icon={<FileEdit className="w-4 h-4" />} label="Rascunhos" value={stats.drafts} tone="warning" />
      </motion.div>

      {/* Search */}
      {flows.length > 0 && (
        <div className="relative max-w-sm">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <Input placeholder="Buscar workflows..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" />
        </div>
      )}

      {/* Empty state */}
      {flows.length === 0 && <EmptyState onCreate={() => setCreateOpen(true)} />}

      {/* Grid */}
      {filteredFlows.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <AnimatePresence mode="popLayout">
            {filteredFlows.map((flow, i) => (
              <motion.div
                key={flow.id}
                layout
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.25, delay: Math.min(i * 0.03, 0.3) }}
              >
                <FlowCard
                  flow={flow}
                  onEdit={() => router.push(`/workflows/${flow.id}`)}
                  onDuplicate={() => handleDuplicate(flow)}
                  onTogglePublish={() => handleTogglePublish(flow)}
                  onDelete={() => setDeleteTarget(flow)}
                  onSessions={() => setSessionsTarget(flow)}
                  formatRelative={formatRelative}
                />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {filteredFlows.length === 0 && flows.length > 0 && (
        <div className="text-center py-12 text-muted-foreground text-sm">
          Nenhum workflow encontrado para &ldquo;{search}&rdquo;.
        </div>
      )}

      {/* Modal de criação */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-primary" />
              Novo workflow
            </DialogTitle>
            <DialogDescription>
              Dê um nome e uma descrição curta. Você vai desenhar o fluxo no editor visual em seguida.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="flow-name">Nome</Label>
              <Input
                id="flow-name"
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Ex: Atendimento inicial WhatsApp"
                maxLength={255}
                onKeyDown={(e) => { if (e.key === 'Enter' && !creating) handleCreate(); }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="flow-desc">Descrição (opcional)</Label>
              <Textarea
                id="flow-desc"
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Ex: menu inicial com opções de boleto, atendente e segunda via."
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)} disabled={creating}>Cancelar</Button>
            <Button onClick={handleCreate} disabled={creating}>
              {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Criar e abrir editor'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirmação de exclusão */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir workflow?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta ação não pode ser desfeita. O workflow{' '}
              <strong className="text-foreground">&ldquo;{deleteTarget?.name}&rdquo;</strong> será removido permanentemente.
              Se estiver ativo em algum canal, troque o fluxo ativo antes de excluir.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleting ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Excluir'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <SessionsDrawer
        open={!!sessionsTarget}
        flowId={sessionsTarget?.id ?? null}
        flowName={sessionsTarget?.name ?? ''}
        onClose={() => setSessionsTarget(null)}
      />
    </div>
  );
}

// ============================================================
// Sub-componentes
// ============================================================
function StatCard({ icon, label, value, tone }: {
  icon: React.ReactNode; label: string; value: number;
  tone: 'neutral' | 'success' | 'warning';
}) {
  const toneClasses = {
    neutral: 'bg-muted text-muted-foreground',
    success: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
    warning: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  }[tone];

  return (
    <div className="rounded-xl border border-border bg-card p-4 flex items-center gap-3">
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${toneClasses}`}>{icon}</div>
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-xl font-semibold text-foreground tabular-nums">{value}</p>
      </div>
    </div>
  );
}

function FlowCard({ flow, onEdit, onDuplicate, onTogglePublish, onDelete, onSessions, formatRelative }: {
  flow: Flow; onEdit: () => void; onDuplicate: () => void;
  onTogglePublish: () => void; onDelete: () => void; onSessions: () => void;
  formatRelative: (iso: string) => string;
}) {
  return (
    <div
      className="group relative rounded-xl border border-border bg-card p-5 transition-all hover:shadow-lg hover:border-primary/30 cursor-pointer"
      onClick={onEdit}
    >
      <div className={`absolute top-0 left-0 right-0 h-[3px] rounded-t-xl transition-opacity ${
        flow.is_published
          ? 'bg-gradient-to-r from-emerald-400 to-emerald-600'
          : 'bg-gradient-to-r from-muted to-muted opacity-60'
      }`} />

      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2.5 min-w-0 flex-1">
          <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
            <MessageSquareText className="w-4 h-4 text-primary" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <h3 className="font-semibold text-foreground truncate text-[15px]">{flow.name}</h3>
              <span
                className={
                  flow.kind === 'broadcast'
                    ? 'inline-flex items-center text-[10px] font-semibold px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-700 dark:text-rose-400'
                    : 'inline-flex items-center text-[10px] font-semibold px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-400'
                }
              >
                {flow.kind === 'broadcast' ? 'Broadcast' : 'Chatbot'}
              </span>
            </div>
            <p className="text-xs text-muted-foreground truncate">
              {flow.is_published ? `v${flow.version} \u00b7 publicado` : 'rascunho'}
            </p>
          </div>
        </div>

        <div onClick={(e) => e.stopPropagation()}>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity">
                <MoreVertical className="w-4 h-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuItem onClick={onEdit}><Pencil className="w-4 h-4 mr-2" /> Editar</DropdownMenuItem>
              <DropdownMenuItem onClick={onSessions}><Users className="w-4 h-4 mr-2" /> Ver sessões</DropdownMenuItem>
              <DropdownMenuItem onClick={onTogglePublish}>
                {flow.is_published ? <><Pause className="w-4 h-4 mr-2" /> Despublicar</> : <><Play className="w-4 h-4 mr-2" /> Publicar</>}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={onDuplicate}><Copy className="w-4 h-4 mr-2" /> Duplicar</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={onDelete} className="text-destructive focus:text-destructive">
                <Trash2 className="w-4 h-4 mr-2" /> Excluir
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <p className="text-sm text-muted-foreground mb-4 line-clamp-2 min-h-[2.5rem]">
        {flow.description || 'Sem descrição.'}
      </p>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {flow.is_published ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Ativo
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-medium">
              Rascunho
            </span>
          )}
        </span>
        <span>Atualizado {formatRelative(flow.updated_at)}</span>
      </div>
    </div>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4 }}
      className="text-center py-16 px-4 rounded-2xl border-2 border-dashed border-border bg-gradient-to-b from-card to-background"
    >
      <div className="mx-auto w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
        <Workflow className="w-8 h-8 text-primary" />
      </div>
      <h3 className="text-lg font-semibold text-foreground mb-2">Crie seu primeiro workflow</h3>
      <p className="text-sm text-muted-foreground max-w-md mx-auto mb-6">
        Desenhe fluxos visuais com botões, perguntas e transferência para humano — sem escrever código.
      </p>
      <Button onClick={onCreate} size="lg" className="gap-2">
        <Plus className="w-4 h-4" />
        Novo workflow
      </Button>
    </motion.div>
  );
}

export default function ChatbotPage() {
  return (
    <ChatbotListContent />
  );
}
