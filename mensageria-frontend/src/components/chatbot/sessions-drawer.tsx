'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X, Users, Clock, CheckCircle2, XCircle, Loader2, RefreshCw, Phone, Ban, FastForward,
} from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface Session {
  id: number;
  contact_wa_id: string;
  contact_name: string;
  current_node_id: string | null;
  status: 'active' | 'waiting' | 'completed' | 'cancelled' | 'timeout';
  variables: Record<string, any>;
  started_at: string | null;
  last_interaction_at: string | null;
  completed_at: string | null;
  next_resume_at: string | null;
}

type TabKey = 'active' | 'waiting' | 'completed' | 'cancelled';

const TABS: { key: TabKey; label: string; icon: React.ComponentType<{ className?: string }>; color: string }[] = [
  { key: 'active', label: 'Ativas', icon: Clock, color: 'text-emerald-600 dark:text-emerald-400' },
  { key: 'waiting', label: 'Aguardando', icon: Clock, color: 'text-amber-600 dark:text-amber-400' },
  { key: 'completed', label: 'Concluídas', icon: CheckCircle2, color: 'text-blue-600 dark:text-blue-400' },
  { key: 'cancelled', label: 'Canceladas', icon: XCircle, color: 'text-gray-500' },
];

interface Props {
  open: boolean;
  flowId: number | null;
  flowName: string;
  onClose: () => void;
}

export function SessionsDrawer({ open, flowId, flowName, onClose }: Props) {
  const [tab, setTab] = useState<TabKey>('active');
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchSessions = useCallback(async () => {
    if (!flowId) return;
    setLoading(true);
    try {
      const statusQuery = tab === 'cancelled' ? 'all' : tab;
      const res = await api.get(`/chatbot/flows/${flowId}/sessions`, {
        params: { status: statusQuery, limit: 50 },
      });
      let list: Session[] = res.data || [];
      if (tab === 'cancelled') {
        list = list.filter((s) => s.status === 'cancelled' || s.status === 'timeout');
      }
      setSessions(list);
    } catch {
      // silencioso
    } finally {
      setLoading(false);
    }
  }, [flowId, tab]);

  useEffect(() => {
    if (!open || !flowId) return;
    fetchSessions();
  }, [open, flowId, fetchSessions]);

  useEffect(() => {
    if (!open || !flowId) return;
    if (tab !== 'active' && tab !== 'waiting') return;
    const iv = setInterval(fetchSessions, 10000);
    return () => clearInterval(iv);
  }, [open, flowId, tab, fetchSessions]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  const handleCancel = async (session: Session) => {
    if (!flowId) return;
    if (!confirm(`Cancelar sessão de ${session.contact_name}?`)) return;
    try {
      await api.delete(`/chatbot/flows/${flowId}/sessions/${session.id}`);
      toast.success('Sessão cancelada');
      fetchSessions();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e.response?.data?.detail || 'Erro ao cancelar');
    }
  };

  const handleResumeNow = async (session: Session) => {
    if (!flowId) return;
    try {
      await api.post(`/chatbot/flows/${flowId}/sessions/${session.id}/resume-now`);
      toast.success('Retomada antecipada — vai processar no próximo ciclo');
      setTimeout(fetchSessions, 1500);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e.response?.data?.detail || 'Erro ao retomar');
    }
  };

  const fmtFuture = (iso: string) => {
    try {
      const d = new Date(iso);
      const diff = d.getTime() - Date.now();
      if (diff < 0) return 'agora';
      const mins = Math.floor(diff / 60000);
      if (mins < 1) return 'em instantes';
      if (mins < 60) return `em ${mins} min`;
      const hours = Math.floor(mins / 60);
      if (hours < 24) return `em ${hours}h`;
      const days = Math.floor(hours / 24);
      return `em ${days} dia${days > 1 ? 's' : ''}`;
    } catch { return 'em breve'; }
  };

  const fmt = (iso: string | null) => {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      const diff = Date.now() - d.getTime();
      const mins = Math.floor(diff / 60000);
      if (mins < 1) return 'agora';
      if (mins < 60) return `há ${mins} min`;
      const hours = Math.floor(mins / 60);
      if (hours < 24) return `há ${hours}h`;
      return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    } catch { return '—'; }
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40"
          />

          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 280 }}
            className="fixed top-0 right-0 bottom-0 w-full sm:w-[480px] bg-card border-l border-border z-50 flex flex-col shadow-2xl"
          >
            <div className="flex items-start justify-between p-5 border-b border-border">
              <div className="min-w-0 flex-1">
                <div className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-1">
                  Sessões do workflow
                </div>
                <h2 className="text-lg font-semibold text-foreground truncate">{flowName}</h2>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <Button size="icon" variant="ghost" onClick={fetchSessions} disabled={loading} className="h-8 w-8">
                  <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
                </Button>
                <Button size="icon" variant="ghost" onClick={onClose} className="h-8 w-8">
                  <X className="w-4 h-4" />
                </Button>
              </div>
            </div>

            <div className="flex border-b border-border">
              {TABS.map((t) => {
                const active = tab === t.key;
                const Icon = t.icon;
                return (
                  <button
                    key={t.key}
                    onClick={() => setTab(t.key)}
                    className={cn(
                      'flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium border-b-2 transition-colors',
                      active ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
                    )}
                  >
                    <Icon className={cn('w-3.5 h-3.5', active && t.color)} />
                    {t.label}
                  </button>
                );
              })}
            </div>

            <div className="flex-1 overflow-y-auto">
              {loading && sessions.length === 0 && (
                <div className="flex items-center justify-center py-16">
                  <Loader2 className="w-5 h-5 animate-spin text-primary" />
                </div>
              )}

              {!loading && sessions.length === 0 && (
                <div className="flex flex-col items-center justify-center py-16 px-8 text-center">
                  <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
                    <Users className="w-5 h-5 text-muted-foreground" />
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {tab === 'active' && 'Nenhuma sessão ativa no momento.'}
                    {tab === 'waiting' && 'Nenhuma sessão aguardando retomada.'}
                    {tab === 'completed' && 'Nenhuma sessão concluída ainda.'}
                    {tab === 'cancelled' && 'Nenhuma sessão cancelada.'}
                  </p>
                </div>
              )}

              <ul className="divide-y divide-border">
                {sessions.map((s) => (
                  <SessionItem
                    key={s.id}
                    session={s}
                    onCancel={tab === 'active' || tab === 'waiting' ? () => handleCancel(s) : undefined}
                    onResumeNow={tab === 'waiting' ? () => handleResumeNow(s) : undefined}
                    fmt={fmt}
                    fmtFuture={fmtFuture}
                  />
                ))}
              </ul>
            </div>

            {tab === 'active' && (
              <div className="p-3 border-t border-border bg-muted/30 text-[11px] text-muted-foreground text-center">
                Atualiza automaticamente a cada 10 segundos
              </div>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function SessionItem({
  session, onCancel, onResumeNow, fmt, fmtFuture,
}: {
  session: Session;
  onCancel?: () => void;
  onResumeNow?: () => void;
  fmt: (iso: string | null) => string;
  fmtFuture: (iso: string) => string;
}) {
  const [expanded, setExpanded] = useState(false);
  const vars = session.variables || {};
  const varEntries = Object.entries(vars);

  const statusBadge = {
    active: { label: 'Ativa', classes: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' },
    waiting: { label: 'Aguardando', classes: 'bg-amber-500/10 text-amber-600 dark:text-amber-400' },
    completed: { label: 'Concluída', classes: 'bg-blue-500/10 text-blue-600 dark:text-blue-400' },
    cancelled: { label: 'Cancelada', classes: 'bg-gray-500/10 text-gray-600 dark:text-gray-400' },
    timeout: { label: 'Timeout', classes: 'bg-orange-500/10 text-orange-600 dark:text-orange-400' },
  }[session.status];

  return (
    <li className="p-4 hover:bg-muted/30 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <button onClick={() => setExpanded((v) => !v)} className="flex-1 min-w-0 text-left">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-medium text-foreground truncate">{session.contact_name}</span>
            <span className={cn('text-[10px] font-semibold px-1.5 py-0.5 rounded-full', statusBadge.classes)}>
              {statusBadge.label}
            </span>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <Phone className="w-3 h-3" />
            <span className="font-mono">{session.contact_wa_id}</span>
            <span>&middot;</span>
            <span>{fmt(session.last_interaction_at)}</span>
          </div>
        </button>
        <div className="flex items-center gap-1 flex-shrink-0">
          {onResumeNow && (
            <Button size="icon" variant="ghost" onClick={onResumeNow} className="h-7 w-7 text-muted-foreground hover:text-primary" title="Retomar agora">
              <FastForward className="w-3.5 h-3.5" />
            </Button>
          )}
          {onCancel && (
            <Button size="icon" variant="ghost" onClick={onCancel} className="h-7 w-7 text-muted-foreground hover:text-destructive" title="Cancelar sessão">
              <Ban className="w-3.5 h-3.5" />
            </Button>
          )}
        </div>
      </div>

      {session.status === 'waiting' && session.next_resume_at && (
        <div className="mt-2 flex items-center gap-1.5 text-[11px] text-amber-600 dark:text-amber-400">
          <Clock className="w-3 h-3" />
          Retoma {fmtFuture(session.next_resume_at)}
        </div>
      )}

      {expanded && varEntries.length > 0 && (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="mt-3 pt-3 border-t border-border/50">
          <p className="text-[10px] uppercase font-semibold tracking-wider text-muted-foreground mb-2">Variáveis capturadas</p>
          <div className="space-y-1">
            {varEntries.map(([k, v]) => (
              <div key={k} className="flex items-center gap-2 text-[11px]">
                <code className="text-primary font-mono">{`{${k}}`}</code>
                <span className="text-muted-foreground">=</span>
                <span className="text-foreground truncate">{String(v)}</span>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </li>
  );
}
