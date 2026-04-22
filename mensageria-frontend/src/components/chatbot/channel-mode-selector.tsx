'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  Sparkles, Workflow, CircleSlash, Loader2, AlertTriangle, ChevronRight,
} from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

export type OperationMode = 'ai' | 'chatbot' | 'none';

export interface ChannelModeState {
  operation_mode: OperationMode;
  active_chatbot_flow_id: number | null;
  active_chatbot_flow_name?: string | null;
}

export interface PublishedFlow {
  id: number;
  name: string;
}

interface Props {
  channelId: number;
  channelName: string;
  mode: ChannelModeState;
  publishedFlows: PublishedFlow[];
  onChange: (next: ChannelModeState) => void;
}

const MODES: {
  value: OperationMode;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  activeClass: string;
  iconColor: string;
}[] = [
  {
    value: 'ai',
    label: 'IA',
    icon: Sparkles,
    activeClass: 'bg-white shadow-sm text-violet-700 dark:text-violet-300',
    iconColor: 'text-violet-600 dark:text-violet-400',
  },
  {
    value: 'chatbot',
    label: 'Workflow',
    icon: Workflow,
    activeClass: 'bg-white shadow-sm text-indigo-700 dark:text-indigo-300',
    iconColor: 'text-indigo-600 dark:text-indigo-400',
  },
  {
    value: 'none',
    label: 'Nenhum',
    icon: CircleSlash,
    activeClass: 'bg-white shadow-sm text-gray-700 dark:text-gray-300',
    iconColor: 'text-gray-500',
  },
];

export function ChannelModeSelector({
  channelId, channelName, mode, publishedFlows, onChange,
}: Props) {
  const [saving, setSaving] = useState(false);
  const hasPublished = publishedFlows.length > 0;

  const apply = async (nextMode: OperationMode, flowId?: number | null) => {
    if (saving) return;

    if (nextMode === 'chatbot' && !flowId && !hasPublished) {
      toast.error('Publique um workflow antes de ativar neste canal');
      return;
    }

    // Confirmações de exclusividade (só ao TROCAR de modo)
    const currentMode = mode.operation_mode;
    if (currentMode !== nextMode) {
      if (currentMode === 'ai' && nextMode === 'chatbot') {
        const ok = confirm(
          `O canal "${channelName}" está com o Agente de IA ativo. `
          + `Ativar um Workflow vai DESATIVAR a IA neste canal. Continuar?`
        );
        if (!ok) return;
      } else if (currentMode === 'chatbot' && nextMode === 'ai') {
        const flowName = mode.active_chatbot_flow_name || 'atual';
        const ok = confirm(
          `O canal "${channelName}" tem o workflow "${flowName}" rodando. `
          + `Ativar a IA aqui vai DESATIVAR o workflow e cancelar as sessões em andamento. Continuar?`
        );
        if (!ok) return;
      } else if (currentMode === 'chatbot' && nextMode === 'none') {
        const flowName = mode.active_chatbot_flow_name || 'atual';
        const ok = confirm(
          `Desativar o workflow "${flowName}" em "${channelName}" `
          + `vai cancelar as sessões em andamento. Continuar?`
        );
        if (!ok) return;
      }
    }

    let finalFlowId: number | null = null;
    if (nextMode === 'chatbot') {
      finalFlowId = flowId ?? mode.active_chatbot_flow_id ?? publishedFlows[0]?.id ?? null;
      if (!finalFlowId) return;
    }

    setSaving(true);
    try {
      const res = await api.put(`/chatbot/channels/${channelId}/mode`, {
        operation_mode: nextMode,
        active_chatbot_flow_id: nextMode === 'chatbot' ? finalFlowId : null,
        force: true,  // sempre força (a confirmação já foi visual)
      });
      const chosenFlow = publishedFlows.find((f) => f.id === finalFlowId);
      onChange({
        operation_mode: res.data.operation_mode,
        active_chatbot_flow_id: res.data.active_chatbot_flow_id,
        active_chatbot_flow_name: chosenFlow?.name ?? null,
      });
      toast.success('Modo atualizado');
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e.response?.data?.detail || 'Erro ao atualizar modo');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-4 pt-4 border-t border-gray-100 dark:border-border/50">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-medium text-gray-600 dark:text-muted-foreground">
            Modo de operação
          </span>
          {saving && <Loader2 className="w-3 h-3 animate-spin text-gray-400" />}
        </div>

        <div
          role="tablist"
          aria-label={`Modo de operação de ${channelName}`}
          className="inline-flex rounded-lg bg-gray-100 dark:bg-muted p-1 gap-0.5"
        >
          {MODES.map((m) => {
            const active = mode.operation_mode === m.value;
            const Icon = m.icon;
            return (
              <button
                key={m.value}
                role="tab"
                aria-selected={active}
                onClick={() => apply(m.value)}
                disabled={saving}
                className={cn(
                  'inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium rounded-md transition-all whitespace-nowrap',
                  active
                    ? m.activeClass
                    : 'text-gray-500 dark:text-muted-foreground hover:text-gray-700 dark:hover:text-foreground',
                  saving && 'opacity-60 cursor-not-allowed',
                )}
              >
                <Icon className={cn('w-3.5 h-3.5', active ? m.iconColor : '')} />
                {m.label}
              </button>
            );
          })}
        </div>
      </div>

      {mode.operation_mode === 'chatbot' && (
        <div className="mt-3">
          {hasPublished ? (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[11px] text-gray-500 dark:text-muted-foreground">Fluxo ativo:</span>
              <select
                value={mode.active_chatbot_flow_id || ''}
                onChange={(e) => apply('chatbot', Number(e.target.value))}
                disabled={saving}
                className="px-2.5 py-1 text-[12px] bg-gray-50 dark:bg-muted border border-gray-200 dark:border-border rounded-md text-gray-700 dark:text-foreground focus:outline-none focus:border-primary cursor-pointer disabled:opacity-60"
              >
                {publishedFlows.map((f) => (
                  <option key={f.id} value={f.id}>{f.name}</option>
                ))}
              </select>
              <Link href="/workflows" className="ml-auto inline-flex items-center gap-0.5 text-[11px] text-primary hover:underline">
                Gerenciar <ChevronRight className="w-3 h-3" />
              </Link>
            </div>
          ) : (
            <div className="flex items-start gap-2 px-3 py-2 rounded-md bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30">
              <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <div className="text-[11px] text-amber-800 dark:text-amber-200 leading-snug">
                Você não tem workflows publicados.{' '}
                <Link href="/workflows" className="font-semibold underline">Criar um agora &rarr;</Link>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
