"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { format, parseISO } from "date-fns";
import { ptBR } from "date-fns/locale";
import axios from "axios";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  FileText,
  Image as ImageIcon,
  Mic,
  Search,
  Send,
  Video,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { BrandInstagram, BrandWhatsApp, ChannelIcon } from "@/components/brand/channel-icon";
import { listPipelines, moveCard } from "@/lib/api-crm";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { Channel, Contact, Message, PipelineColumn } from "@/types/api";

interface ContactListResp {
  total: number;
  items: Contact[];
}

type ChannelTab = "all" | "whatsapp" | "instagram";

const POLL_INTERVAL = 10_000;

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

function fmtTime(dateStr: string | null) {
  if (!dateStr) return "";
  try {
    return format(parseISO(dateStr), "HH:mm", { locale: ptBR });
  } catch {
    return "";
  }
}

/** Remove o prefixo interno ig: dos contatos de Instagram. */
function stripIg(waId: string) {
  return waId.startsWith("ig:") ? waId.slice(3) : waId;
}

const kindOf = (provider?: string | null): ChannelTab =>
  provider === "instagram" ? "instagram" : "whatsapp";

/** 5515997567886 → +55 15 99756-7886 (só pra WhatsApp). */
function formatPhone(raw: string | null | undefined): string {
  if (!raw) return "";
  const digits = String(raw).split("@")[0].replace(/\D/g, "");
  if (digits.length < 10) return raw;
  const country = digits.startsWith("55") ? digits.slice(0, 2) : "";
  const rest = country ? digits.slice(2) : digits;
  const ddd = rest.slice(0, 2);
  const phone = rest.slice(2);
  const p1 = phone.length > 8 ? phone.slice(0, phone.length - 4) : phone.slice(0, -4);
  const p2 = phone.slice(-4);
  return `${country ? "+" + country + " " : ""}${ddd} ${p1}-${p2}`;
}

const AVATAR_COLORS = [
  "bg-emerald-500",
  "bg-teal-500",
  "bg-sky-500",
  "bg-violet-500",
  "bg-fuchsia-500",
  "bg-amber-500",
  "bg-rose-500",
];

function avatarColor(seed: string) {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

function initialOf(name: string) {
  const t = name.trim();
  return t ? t[0].toUpperCase() : "?";
}

const MEDIA_TYPES = new Set(["image", "audio", "video", "document", "sticker", "file"]);

function MediaPlaceholder({ type, caption }: { type: string; caption?: string }) {
  const Icon =
    type === "image" || type === "sticker"
      ? ImageIcon
      : type === "audio"
        ? Mic
        : type === "video"
          ? Video
          : FileText;
  const label =
    type === "image"
      ? "Imagem"
      : type === "sticker"
        ? "Figurinha"
        : type === "audio"
          ? "Áudio"
          : type === "video"
            ? "Vídeo"
            : "Documento";
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2 rounded-md bg-background/40 px-2 py-1.5 text-xs">
        <Icon className="h-4 w-4 shrink-0 opacity-80" />
        <span className="opacity-90">{label}</span>
      </div>
      {caption && <div className="whitespace-pre-wrap text-sm">{caption}</div>}
    </div>
  );
}

function MessageContent({ m }: { m: Message }) {
  const content = m.content || "";
  // Mídia baixada (WhatsApp): "local:filename|mime|caption"
  if (content.startsWith("local:")) {
    const rest = content.slice("local:".length);
    const parts = rest.split("|");
    const caption = parts[2] || "";
    return <MediaPlaceholder type={m.message_type} caption={caption} />;
  }
  // Marcador de mídia (Instagram, sem download): "[image] url" / "[audio]" etc.
  if (MEDIA_TYPES.has(m.message_type)) {
    const caption = content.replace(/^\[[a-z_]+\]\s*/i, "").trim();
    return <MediaPlaceholder type={m.message_type} caption={caption && !caption.startsWith("http") ? caption : ""} />;
  }
  if (!content) return <span className="opacity-70">{`[${m.message_type}]`}</span>;
  return <div className="whitespace-pre-wrap">{content}</div>;
}

export default function ConversationsPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [selected, setSelected] = useState<Contact | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  const [tab, setTab] = useState<ChannelTab>("all");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [activeChannelId, setActiveChannelId] = useState<number | null>(null);
  const [stageColumns, setStageColumns] = useState<PipelineColumn[]>([]);
  const deepLinkDone = useRef(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const loadContacts = useCallback(async () => {
    setLoadingList(true);
    try {
      const [cRes, chRes] = await Promise.all([
        api.get<ContactListResp>("/contacts", { params: { limit: 200 } }),
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

  const loadMessages = useCallback(async (contact: Contact, silent = false) => {
    if (!silent) setLoadingMsgs(true);
    try {
      const res = await api.get<Message[]>(`/contacts/${contact.id}/messages`, {
        params: { limit: 50 },
      });
      setMessages(res.data);
    } catch (err) {
      if (!silent) toast.error(errMsg(err, "Falha ao carregar mensagens"));
    } finally {
      if (!silent) setLoadingMsgs(false);
    }
  }, []);

  useEffect(() => {
    loadContacts();
  }, [loadContacts]);

  // Etapas do funil (do pipeline default) pro dropdown de etapa na thread.
  useEffect(() => {
    listPipelines()
      .then((ps) => {
        const def = ps.find((p) => p.is_default) || ps[0];
        if (def) setStageColumns([...def.columns].sort((a, b) => a.order - b.order));
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selected) {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(() => loadMessages(selected, true), POLL_INTERVAL);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [selected, loadMessages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const channelById = useMemo(() => {
    const m = new Map<number, Channel>();
    channels.forEach((c) => m.set(c.id, c));
    return m;
  }, [channels]);

  const channelOf = useCallback(
    (contact: Contact | null) =>
      contact?.channel_id != null ? channelById.get(contact.channel_id) ?? null : null,
    [channelById],
  );

  const providerOf = useCallback(
    (contact: Contact) => channelOf(contact)?.provider,
    [channelOf],
  );

  // Filtro base (canal ativo + busca + status) — sem a aba, pra contar por aba.
  const baseFiltered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return contacts.filter((c) => {
      if (activeChannelId != null && c.channel_id !== activeChannelId) return false;
      if (statusFilter && c.lead_status !== statusFilter) return false;
      if (q) {
        const hay = `${c.name || ""} ${stripIg(c.wa_id)}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [contacts, activeChannelId, statusFilter, search]);

  const counts = useMemo(() => {
    let wpp = 0;
    let ig = 0;
    baseFiltered.forEach((c) => (kindOf(providerOf(c)) === "instagram" ? ig++ : wpp++));
    return { all: baseFiltered.length, whatsapp: wpp, instagram: ig };
  }, [baseFiltered, providerOf]);

  const visibleContacts = useMemo(
    () => baseFiltered.filter((c) => tab === "all" || kindOf(providerOf(c)) === tab),
    [baseFiltered, tab, providerOf],
  );

  const statuses = useMemo(() => {
    const set = new Set<string>();
    contacts.forEach((c) => c.lead_status && set.add(c.lead_status));
    return Array.from(set);
  }, [contacts]);

  const openContact = (contact: Contact) => {
    setSelected(contact);
    setMessages([]);
    loadMessages(contact);
  };

  // Deep-link do CRM: /conversations?contact=<id> abre a conversa daquele lead.
  useEffect(() => {
    if (deepLinkDone.current || contacts.length === 0) return;
    const idStr = new URLSearchParams(window.location.search).get("contact");
    if (!idStr) return;
    const target = contacts.find((c) => c.id === Number(idStr));
    if (target) {
      deepLinkDone.current = true;
      openContact(target);
    }
  }, [contacts]); // eslint-disable-line react-hooks/exhaustive-deps

  // Mudar etapa do lead a partir da conversa (mesma fonte: Contact.lead_status).
  const changeStage = async (status: string) => {
    if (!selected) return;
    const prev = selected.lead_status;
    setSelected({ ...selected, lead_status: status });
    setContacts((cs) => cs.map((c) => (c.id === selected.id ? { ...c, lead_status: status } : c)));
    try {
      await moveCard(selected.id, status);
    } catch {
      toast.error("Falha ao mudar etapa");
      setSelected((s) => (s ? { ...s, lead_status: prev } : s));
      setContacts((cs) => cs.map((c) => (c.id === selected.id ? { ...c, lead_status: prev } : c)));
    }
  };

  // Envio roteado por provider — PORTADO DA SPRINT 3, sem alteração de comportamento.
  const send = async () => {
    if (!selected || !input.trim() || !selected.channel_id) return;
    const ch = channelById.get(selected.channel_id);
    if (!ch) {
      toast.error("Canal do contato não encontrado");
      return;
    }
    if (ch.provider === "evolution" && !ch.instance_name) {
      toast.error("Canal sem instance_name");
      return;
    }
    setSending(true);
    try {
      if (ch.provider === "instagram") {
        const to = selected.wa_id.startsWith("ig:") ? selected.wa_id.slice(3) : selected.wa_id;
        await api.post(`/instagram/channels/${ch.id}/send-text`, { to, text: input });
      } else if (ch.provider === "official") {
        await api.post(`/meta/channels/${ch.id}/send-text`, { to: selected.wa_id, text: input });
      } else {
        await api.post("/evolution/send", null, {
          params: { instance_name: ch.instance_name, to: selected.wa_id, text: input },
        });
      }
      setInput("");
      await loadMessages(selected, true);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao enviar"));
    } finally {
      setSending(false);
    }
  };

  const activeChannel = activeChannelId != null ? channelById.get(activeChannelId) ?? null : null;
  const channelSubtitle = (ch: Channel) =>
    ch.provider === "instagram"
      ? ch.instagram_id
        ? `@${ch.name.replace(/^@/, "")}`
        : ch.name
      : formatPhone(ch.phone_number) || "WhatsApp";

  const TABS: { key: ChannelTab; label: string; count: number }[] = [
    { key: "all", label: "Todos", count: counts.all },
    { key: "whatsapp", label: "WhatsApp", count: counts.whatsapp },
    { key: "instagram", label: "Instagram", count: counts.instagram },
  ];

  return (
    <div className="-m-6 flex h-[calc(100vh-3.5rem)] bg-background">
      {/* ---------- Lista ---------- */}
      <div
        className={cn(
          "w-full shrink-0 flex-col border-r border-border bg-card lg:flex lg:w-[350px]",
          selected ? "hidden lg:flex" : "flex",
        )}
      >
        {/* Seletor de canal */}
        <div className="border-b border-border p-3">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex w-full items-center gap-3 rounded-lg border border-border bg-background p-2.5 text-left transition-colors hover:bg-muted">
                {activeChannel ? (
                  <ChannelIcon provider={activeChannel.provider} size={36} />
                ) : (
                  <div className="flex h-9 w-9 items-center justify-center rounded-[28%] bg-primary/10">
                    <BrandWhatsApp size={20} bare />
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold">
                    {activeChannel ? activeChannel.name : "Todos os canais"}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {activeChannel ? channelSubtitle(activeChannel) : "Conversas de todos os canais"}
                  </div>
                </div>
                <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-[320px]">
              <DropdownMenuGroup>
                <DropdownMenuLabel>Canais</DropdownMenuLabel>
              </DropdownMenuGroup>
              <DropdownMenuItem onClick={() => setActiveChannelId(null)}>
                <div className="flex h-7 w-7 items-center justify-center rounded-[28%] bg-muted">
                  <BrandWhatsApp size={16} bare />
                </div>
                <span className="flex-1">Todos os canais</span>
                {activeChannelId == null && <Check className="h-4 w-4 text-primary" />}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              {channels.length === 0 && (
                <div className="px-2 py-1.5 text-xs text-muted-foreground">Nenhum canal.</div>
              )}
              {channels.map((c) => (
                <DropdownMenuItem key={c.id} onClick={() => setActiveChannelId(c.id)}>
                  <ChannelIcon provider={c.provider} size={28} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate">{c.name}</div>
                    <div className="truncate text-xs text-muted-foreground">
                      {channelSubtitle(c)}
                    </div>
                  </div>
                  {activeChannelId === c.id && <Check className="h-4 w-4 text-primary" />}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Tabs por canal */}
        <div className="flex gap-1 border-b border-border p-2">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors",
                tab === t.key
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted",
              )}
            >
              {t.key === "whatsapp" && <BrandWhatsApp size={14} bare />}
              {t.key === "instagram" && <BrandInstagram size={14} />}
              {t.label}
              <span
                className={cn(
                  "rounded-full px-1.5 text-[10px]",
                  tab === t.key ? "bg-primary/15" : "bg-muted",
                )}
              >
                {t.count}
              </span>
            </button>
          ))}
        </div>

        {/* Busca */}
        <div className="border-b border-border p-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar conversa…"
              className="pl-8"
            />
          </div>
        </div>

        {/* Status filter */}
        {statuses.length > 0 && (
          <div className="flex flex-wrap gap-1.5 border-b border-border p-2">
            <button
              onClick={() => setStatusFilter(null)}
              className={cn(
                "rounded-full px-2.5 py-1 text-xs transition-colors",
                statusFilter == null
                  ? "bg-primary/10 text-primary"
                  : "bg-muted text-muted-foreground hover:bg-muted/70",
              )}
            >
              Todos
            </button>
            {statuses.map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={cn(
                  "rounded-full px-2.5 py-1 text-xs capitalize transition-colors",
                  statusFilter === s
                    ? "bg-primary/10 text-primary"
                    : "bg-muted text-muted-foreground hover:bg-muted/70",
                )}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Lista de contatos */}
        <div className="flex-1 overflow-auto">
          {loadingList ? (
            <div className="space-y-2 p-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="h-10 w-10 animate-pulse rounded-full bg-muted" />
                  <div className="flex-1 space-y-2">
                    <div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
                    <div className="h-2.5 w-1/2 animate-pulse rounded bg-muted" />
                  </div>
                </div>
              ))}
            </div>
          ) : visibleContacts.length === 0 ? (
            <div className="p-6 text-center text-sm text-muted-foreground">
              Nenhuma conversa por aqui.
            </div>
          ) : (
            visibleContacts.map((c) => {
              const name = c.name || stripIg(c.wa_id);
              const provider = providerOf(c);
              return (
                <button
                  key={c.id}
                  onClick={() => openContact(c)}
                  className={cn(
                    "flex w-full items-center gap-3 border-b border-border/60 p-3 text-left transition-colors hover:bg-muted/60",
                    selected?.id === c.id && "border-l-2 border-l-primary bg-primary/[0.06] pl-[calc(0.75rem-2px)]",
                  )}
                >
                  <div className="relative shrink-0">
                    <div
                      className={cn(
                        "flex h-10 w-10 items-center justify-center rounded-full text-sm font-semibold text-white",
                        avatarColor(name),
                      )}
                    >
                      {initialOf(name)}
                    </div>
                    <span className="absolute -bottom-0.5 -right-0.5 rounded-full bg-card p-0.5">
                      <ChannelIcon provider={provider} size={14} />
                    </span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{name}</span>
                      <span className="shrink-0 text-[11px] text-muted-foreground">
                        {fmt(c.last_inbound_at)}
                      </span>
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {provider === "instagram" ? stripIg(c.wa_id) : formatPhone(c.wa_id)}
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* ---------- Thread ---------- */}
      <div className={cn("flex-1 flex-col bg-muted", selected ? "flex" : "hidden lg:flex")}>
        {!selected ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 text-muted-foreground">
            <BrandWhatsApp size={48} />
            <p className="text-sm">Selecione uma conversa.</p>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="flex items-center gap-3 border-b border-border bg-card p-3">
              <Button
                size="icon"
                variant="ghost"
                className="lg:hidden"
                onClick={() => setSelected(null)}
              >
                <ArrowLeft className="h-5 w-5" />
              </Button>
              <div
                className={cn(
                  "flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold text-white",
                  avatarColor(selected.name || stripIg(selected.wa_id)),
                )}
              >
                {initialOf(selected.name || stripIg(selected.wa_id))}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold">
                  {selected.name || stripIg(selected.wa_id)}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {providerOf(selected) === "instagram"
                    ? stripIg(selected.wa_id)
                    : formatPhone(selected.wa_id)}
                  {selected.lead_status ? ` · ${selected.lead_status}` : ""}
                </div>
              </div>
              {stageColumns.length > 0 && (
                <Select value={selected.lead_status || "novo"} onValueChange={changeStage}>
                  <SelectTrigger className="h-8 w-36 text-xs">
                    <SelectValue placeholder="Etapa" />
                  </SelectTrigger>
                  <SelectContent>
                    {stageColumns.map((col) => (
                      <SelectItem key={col.key} value={col.key} className="text-xs">
                        {col.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <ChannelIcon provider={providerOf(selected)} size={28} />
            </div>

            {/* Mensagens */}
            <div className="flex-1 space-y-1.5 overflow-auto p-4">
              {loadingMsgs ? (
                <div className="space-y-3">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <div
                      key={i}
                      className={cn("flex", i % 2 ? "justify-end" : "justify-start")}
                    >
                      <div className="h-10 w-40 animate-pulse rounded-2xl bg-card" />
                    </div>
                  ))}
                </div>
              ) : messages.length === 0 ? (
                <div className="py-10 text-center text-sm text-muted-foreground">
                  Sem mensagens nessa conversa.
                </div>
              ) : (
                messages.map((m) => (
                  <div
                    key={m.id}
                    className={cn(
                      "flex",
                      m.direction === "outbound" ? "justify-end" : "justify-start",
                    )}
                  >
                    <div
                      className={cn(
                        "max-w-[70%] px-3 py-2 text-sm shadow-sm",
                        m.direction === "outbound"
                          ? "rounded-2xl rounded-br-md bg-primary text-primary-foreground"
                          : "rounded-2xl rounded-bl-md bg-card text-foreground",
                      )}
                    >
                      <MessageContent m={m} />
                      <div
                        className={cn(
                          "mt-1 text-right text-[10px]",
                          m.direction === "outbound"
                            ? "text-primary-foreground/70"
                            : "text-muted-foreground",
                        )}
                      >
                        {fmtTime(m.timestamp)}
                      </div>
                    </div>
                  </div>
                ))
              )}
              <div ref={bottomRef} />
            </div>

            {/* Input */}
            <div className="flex items-end gap-2 border-t border-border bg-card p-3">
              <Textarea
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
                rows={1}
                className="max-h-32 min-h-[40px] resize-none"
              />
              <Button onClick={send} disabled={sending || !input.trim()} size="icon" className="shrink-0">
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
