'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X, RefreshCw, Send, User, Bot, Play,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  initialState, sendUserMessage, clickButton,
  type SimState, type Graph, type SimContact, type ChatBubble,
} from './simulator-engine';

interface Props {
  open: boolean;
  onClose: () => void;
  graph: Graph;
}

const CONTACT: SimContact = { name: 'Lead Teste', wa_id: '5500000000000' };

export function SimulatorDrawer({ open, onClose, graph }: Props) {
  const [state, setState] = useState<SimState>(initialState);
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  // ao reabrir, começa novo
  useEffect(() => {
    if (open) {
      setState(initialState());
      setInput('');
    }
  }, [open]);

  // auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [state.bubbles.length]);

  // ESC fecha
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [open, onClose]);

  const reset = () => { setState(initialState()); setInput(''); };

  const send = (text?: string) => {
    const value = (text ?? input).trim();
    if (!value) return;
    setState((s) => sendUserMessage(s, value, graph, CONTACT));
    setInput('');
  };

  const handleButton = (btn: { id: string; label: string }) => {
    setState((s) => clickButton(s, btn, graph, CONTACT));
  };

  const variables = useMemo(() => Object.entries(state.variables), [state.variables]);
  const canSendMessage = !state.finished && (state.waitKind === null || state.waitKind === 'buttons' || state.waitKind === 'input');

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40"
          />
          <motion.aside
            initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 280 }}
            className="fixed top-0 right-0 bottom-0 w-full sm:w-[460px] bg-card border-l border-border z-50 flex flex-col shadow-2xl"
          >
            {/* Header */}
            <div className="flex items-start justify-between p-4 border-b border-border">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <Play className="w-4 h-4 text-primary" />
                </div>
                <div className="min-w-0">
                  <div className="text-[10px] uppercase font-semibold tracking-widest text-muted-foreground">
                    Simulador
                  </div>
                  <div className="text-sm font-semibold truncate">Testar workflow</div>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={reset}
                  className="h-8 w-8 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  title="Reiniciar conversa"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
                <button
                  onClick={onClose}
                  className="h-8 w-8 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  title="Fechar"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Variáveis capturadas (se houver) */}
            {variables.length > 0 && (
              <div className="px-4 py-2 border-b border-border bg-muted/30">
                <div className="text-[10px] uppercase font-semibold tracking-widest text-muted-foreground mb-1">
                  Variáveis capturadas
                </div>
                <div className="flex flex-wrap gap-1">
                  {variables.map(([k, v]) => (
                    <span key={k} className="inline-flex items-center gap-1 text-[11px] bg-background border border-border rounded-full px-2 py-0.5">
                      <code className="text-primary font-mono">{`{${k}}`}</code>
                      <span className="text-foreground truncate max-w-[120px]">{String(v)}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Chat */}
            <div className="flex-1 overflow-y-auto p-4 space-y-2.5">
              {state.bubbles.length === 0 && (
                <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
                  <div className="w-14 h-14 rounded-full bg-muted flex items-center justify-center mb-3">
                    <Bot className="w-6 h-6 text-muted-foreground" />
                  </div>
                  <p className="text-sm text-muted-foreground mb-1 font-medium">
                    Digite qualquer mensagem pra começar
                  </p>
                  <p className="text-[11px] text-muted-foreground max-w-[260px]">
                    Simulador roda direto no editor, sem enviar WhatsApp real. Use pra testar antes de publicar.
                  </p>
                </div>
              )}

              {state.bubbles.map((b, i) => (
                <Bubble
                  key={i}
                  bubble={b}
                  onButtonClick={handleButton}
                  isLastBotWithButtons={
                    state.waitKind === 'buttons'
                    && b.kind === 'bot'
                    && !!b.buttons?.length
                    && i === state.bubbles.length - 1
                  }
                />
              ))}

              {state.finished && (
                <div className="text-center pt-2 pb-1">
                  <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    Conversa encerrada — clique em <RefreshCw className="w-3 h-3 inline" /> pra reiniciar
                  </span>
                </div>
              )}

              <div ref={bottomRef} />
            </div>

            {/* Input */}
            <div className="p-3 border-t border-border bg-muted/20">
              <form
                onSubmit={(e) => { e.preventDefault(); send(); }}
                className="flex items-center gap-2"
              >
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={
                    state.finished ? 'Conversa encerrada'
                    : state.waitKind === 'buttons' ? 'Clique num botão ou digite o número/texto'
                    : state.waitKind === 'input' ? 'Resposta...'
                    : 'Digite uma mensagem pra iniciar'
                  }
                  disabled={!canSendMessage}
                  className="flex-1 h-9 px-3 rounded-md bg-background border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={!canSendMessage || !input.trim()}
                  className="h-9 w-9 rounded-md bg-primary text-primary-foreground flex items-center justify-center hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                >
                  <Send className="w-4 h-4" />
                </button>
              </form>
              <p className="text-[10px] text-muted-foreground text-center mt-1.5">
                Simulando como <strong>Lead Teste</strong> — sem tocar WhatsApp ou banco
              </p>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function Bubble({
  bubble, onButtonClick, isLastBotWithButtons,
}: {
  bubble: ChatBubble;
  onButtonClick: (b: { id: string; label: string }) => void;
  isLastBotWithButtons: boolean;
}) {
  if (bubble.kind === 'system') {
    return (
      <div className="flex justify-center py-0.5">
        <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground bg-muted/60 border border-border rounded-full px-2.5 py-1">
          {bubble.systemIcon && <span>{bubble.systemIcon}</span>}
          {bubble.text}
        </span>
      </div>
    );
  }

  const isUser = bubble.kind === 'user';

  return (
    <div className={cn('flex gap-2', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
          <Bot className="w-3.5 h-3.5 text-primary" />
        </div>
      )}
      <div className={cn('flex flex-col gap-1.5 max-w-[80%]', isUser && 'items-end')}>
        <div
          className={cn(
            'rounded-2xl px-3.5 py-2 text-sm whitespace-pre-wrap break-words',
            isUser
              ? 'bg-primary text-primary-foreground rounded-br-sm'
              : 'bg-muted text-foreground rounded-bl-sm',
          )}
        >
          {bubble.text}
        </div>
        {!isUser && bubble.buttons && bubble.buttons.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {bubble.buttons.map((btn) => (
              <button
                key={btn.id}
                onClick={() => onButtonClick(btn)}
                disabled={!isLastBotWithButtons}
                className={cn(
                  'text-xs font-medium px-3 py-1.5 rounded-full border transition-all',
                  !isLastBotWithButtons
                    ? 'border-border/50 text-muted-foreground/60 cursor-not-allowed'
                    : 'border-primary/40 text-primary hover:bg-primary hover:text-primary-foreground hover:border-primary active:scale-95',
                )}
              >
                {btn.label}
              </button>
            ))}
          </div>
        )}
      </div>
      {isUser && (
        <div className="w-7 h-7 rounded-full bg-muted flex items-center justify-center flex-shrink-0 mt-0.5">
          <User className="w-3.5 h-3.5 text-muted-foreground" />
        </div>
      )}
    </div>
  );
}
