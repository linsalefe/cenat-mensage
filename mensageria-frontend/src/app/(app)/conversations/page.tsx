"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { format, parseISO } from "date-fns";
import { ptBR } from "date-fns/locale";
import axios from "axios";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { Channel, Contact, Message } from "@/types/api";

interface ContactList {
  total: number;
  items: Contact[];
}

function errMsg(err: unknown, fallback = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fallback;
}

function fmt(dateStr: string | null) {
  if (!dateStr) return "";
  try {
    return format(parseISO(dateStr), "dd/MM HH:mm", { locale: ptBR });
  } catch {
    return dateStr;
  }
}

// Polling a cada 10s pra thread ativa. Lista recarrega só on-demand / ao selecionar.
const POLL_INTERVAL = 10_000;

export default function ConversationsPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [selected, setSelected] = useState<Contact | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadContacts = useCallback(async () => {
    setLoadingList(true);
    try {
      const [cRes, chRes] = await Promise.all([
        api.get<ContactList>("/contacts", { params: { limit: 100 } }),
        api.get<Channel[]>("/chatbot/channels"),
      ]);
      setContacts(cRes.data.items);
      setChannels(chRes.data);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao carregar conversas"));
    } finally {
      setLoadingList(false);
    }
  }, []);

  const loadMessages = useCallback(async (contact: Contact) => {
    try {
      const res = await api.get<Message[]>(`/contacts/${contact.id}/messages`, {
        params: { limit: 50 },
      });
      setMessages(res.data);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao carregar mensagens"));
    }
  }, []);

  useEffect(() => {
    loadContacts();
  }, [loadContacts]);

  // Polling na thread aberta
  useEffect(() => {
    if (!selected) {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(() => {
      loadMessages(selected);
    }, POLL_INTERVAL);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [selected, loadMessages]);

  const openContact = (contact: Contact) => {
    setSelected(contact);
    setMessages([]);
    loadMessages(contact);
  };

  const send = async () => {
    if (!selected || !input.trim() || !selected.channel_id) return;
    const ch = channels.find((c) => c.id === selected.channel_id);
    if (!ch || !ch.instance_name) {
      toast.error("Canal sem instance_name");
      return;
    }
    setSending(true);
    try {
      await api.post("/evolution/send", null, {
        params: { instance_name: ch.instance_name, to: selected.wa_id, text: input },
      });
      setInput("");
      await loadMessages(selected);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao enviar"));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="-m-6 flex h-[calc(100vh-3.5rem)]">
      <div className="flex w-80 shrink-0 flex-col border-r">
        <div className="flex items-center justify-between border-b p-3">
          <h2 className="text-sm font-semibold">Conversas</h2>
          <Button size="sm" variant="ghost" onClick={loadContacts}>
            ↻
          </Button>
        </div>
        <div className="flex-1 overflow-auto">
          {loadingList ? (
            <div className="p-4 text-sm text-muted-foreground">Carregando…</div>
          ) : contacts.length === 0 ? (
            <div className="p-4 text-sm text-muted-foreground">Sem conversas.</div>
          ) : (
            contacts.map((c) => (
              <button
                key={c.id}
                onClick={() => openContact(c)}
                className={cn(
                  "flex w-full flex-col items-start gap-1 border-b p-3 text-left hover:bg-muted",
                  selected?.id === c.id && "bg-muted",
                )}
              >
                <div className="w-full truncate text-sm font-medium">
                  {c.name || c.wa_id}
                </div>
                <div className="flex w-full justify-between text-xs text-muted-foreground">
                  <span className="font-mono">{c.wa_id}</span>
                  <span>{fmt(c.last_inbound_at)}</span>
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      <div className="flex flex-1 flex-col">
        {!selected ? (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
            Selecione uma conversa.
          </div>
        ) : (
          <>
            <div className="border-b p-3">
              <div className="font-medium">{selected.name || selected.wa_id}</div>
              <div className="font-mono text-xs text-muted-foreground">{selected.wa_id}</div>
            </div>
            <div className="flex-1 space-y-2 overflow-auto p-4">
              {messages.length === 0 ? (
                <div className="text-center text-sm text-muted-foreground">
                  Sem mensagens.
                </div>
              ) : (
                messages.map((m) => (
                  <div
                    key={m.id}
                    className={cn(
                      "max-w-md rounded-lg px-3 py-2 text-sm",
                      m.direction === "outbound"
                        ? "ml-auto bg-primary text-primary-foreground"
                        : "bg-muted",
                    )}
                  >
                    <div className="whitespace-pre-wrap">
                      {m.content || `[${m.message_type}]`}
                    </div>
                    <div className="mt-1 text-[10px] opacity-70">{fmt(m.timestamp)}</div>
                  </div>
                ))
              )}
            </div>
            <div className="flex items-center gap-2 border-t p-3">
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder="Digite uma mensagem…"
                disabled={sending}
              />
              <Button onClick={send} disabled={sending || !input.trim()}>
                {sending ? "…" : "Enviar"}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
