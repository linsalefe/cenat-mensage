"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { format, parseISO } from "date-fns";
import { ptBR } from "date-fns/locale";
import axios from "axios";
import {
  ArrowLeft,
  Bot,
  Check,
  CheckCheck,
  ChevronDown,
  Clock,
  FileText,
  FlaskConical,
  Image as ImageIcon,
  Mic,
  PanelRight,
  Plus,
  Search,
  Sparkles,
  UserCheck,
  Video,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { BrandInstagram, BrandWhatsApp, ChannelIcon } from "@/components/brand/channel-icon";
import { Composer } from "@/components/inbox/composer";
import { CrmPanel } from "@/components/inbox/crm-panel";
import {
  countActiveFilters,
  EMPTY_FILTERS,
  FiltersPopover,
  type InboxFilters,
} from "@/components/inbox/filters-popover";
import { NewChatDialog } from "@/components/inbox/new-chat-dialog";
import { TemplateDialog } from "@/components/inbox/template-dialog";
import { listPipelines, moveCard } from "@/lib/api-crm";
import {
  inboxApi,
  tagColorClasses,
  type AgentStatus,
  type AssignableUser,
  type ContactTag,
} from "@/lib/api-inbox";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { Channel, Contact, Message, PipelineColumn } from "@/types/api";

interface ContactListResp {
  total: number;
  items: Contact[];
}

type ChannelTab = "all" | "whatsapp" | "instagram";

const POLL_INTERVAL = 10_000;
const PAGE_TITLE = "Conversas";
/** Distância do fim a partir da qual o botão "descer" aparece. */
const SCROLL_DOWN_THRESHOLD = 300;

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

/** Gradientes do avatar. Hash sobre o nome inteiro (não só a 1ª letra) para
 *  espalhar melhor entre contatos que começam com a mesma letra. */
const AVATAR_COLORS = [
  "bg-gradient-to-br from-emerald-500 to-emerald-700",
  "bg-gradient-to-br from-teal-500 to-teal-700",
  "bg-gradient-to-br from-sky-500 to-sky-700",
  "bg-gradient-to-br from-violet-500 to-violet-700",
  "bg-gradient-to-br from-fuchsia-500 to-fuchsia-700",
  "bg-gradient-to-br from-amber-500 to-amber-700",
  "bg-gradient-to-br from-rose-500 to-rose-700",
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

/** Iniciais para o avatar: "Ana Paula" -> "AP". */
function initialsOf(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Rótulo do separador de data: Hoje / Ontem / dd/MM/yyyy. */
function dayLabel(iso: string | null): string {
  if (!iso) return "";
  try {
    const d = parseISO(iso);
    const hoje = new Date();
    const ontem = new Date();
    ontem.setDate(ontem.getDate() - 1);
    if (d.toDateString() === hoje.toDateString()) return "Hoje";
    if (d.toDateString() === ontem.toDateString()) return "Ontem";
    return format(d, "dd/MM/yyyy", { locale: ptBR });
  } catch {
    return "";
  }
}

/** Agrupa mensagens consecutivas pelo dia, preservando a ordem. */
function groupByDay(msgs: Message[]): Array<{ day: string; items: Message[] }> {
  const out: Array<{ day: string; items: Message[] }> = [];
  for (const m of msgs) {
    const day = dayLabel(m.timestamp);
    const last = out[out.length - 1];
    if (last && last.day === day) last.items.push(m);
    else out.push({ day, items: [m] });
  }
  return out;
}

/** ✓ enviado · ✓✓ entregue · ✓✓ azul lido · ⚠ falhou · 🕐 pendente. */
function MessageStatus({ status }: { status: string }) {
  if (status === "failed")
    return <XCircle className="h-3.5 w-3.5 text-destructive" aria-label="Falha no envio" />;
  if (status === "read")
    return <CheckCheck className="h-3.5 w-3.5 text-wa-check-read" aria-label="Lido" />;
  if (status === "delivered")
    return <CheckCheck className="h-3.5 w-3.5 text-wa-check" aria-label="Entregue" />;
  if (status === "sent")
    return <Check className="h-3.5 w-3.5 text-wa-check" aria-label="Enviado" />;
  return <Clock className="h-3.5 w-3.5 text-wa-check" aria-label="Pendente" />;
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

  const [tab, setTab] = useState<ChannelTab>("all");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [activeChannelId, setActiveChannelId] = useState<number | null>(null);
  const [stageColumns, setStageColumns] = useState<PipelineColumn[]>([]);
  const deepLinkDone = useRef(false);

  const [allTags, setAllTags] = useState<ContactTag[]>([]);
  const [users, setUsers] = useState<AssignableUser[]>([]);
  const [filters, setFilters] = useState<InboxFilters>(EMPTY_FILTERS);
  const [crmOpen, setCrmOpen] = useState(false);
  const [newChatOpen, setNewChatOpen] = useState(false);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [showScrollDown, setShowScrollDown] = useState(false);
  const [tabFocused, setTabFocused] = useState(true);

  // Supervisão do agente de IA.
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [aiOnly, setAiOnly] = useState(false);
  const [togglingAi, setTogglingAi] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);

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

  const loadTags = useCallback(() => {
    inboxApi.listTags().then(setAllTags).catch(() => {});
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
    loadTags();
    inboxApi.assignableUsers().then(setUsers).catch(() => {});
    // Best-effort: se o endpoint não existir/falhar, a tela só não mostra os
    // indicadores de IA — nada quebra.
    inboxApi.agentStatus().then(setAgentStatus).catch(() => {});
  }, [loadContacts, loadTags]);

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

  // A lista precisa continuar chegando para o badge de não lidas atualizar
  // mesmo com a conversa fechada.
  useEffect(() => {
    const id = setInterval(() => loadContacts(), POLL_INTERVAL * 3);
    return () => clearInterval(id);
  }, [loadContacts]);

  // Rolar para o fim só se o usuário já estava no fim — senão ele perderia o
  // ponto onde estava lendo.
  useEffect(() => {
    if (!showScrollDown) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onFocus = () => setTabFocused(true);
    const onBlur = () => setTabFocused(false);
    window.addEventListener("focus", onFocus);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("blur", onBlur);
    };
  }, []);

  const totalUnread = useMemo(
    () => contacts.reduce((acc, c) => acc + (c.unread || 0), 0),
    [contacts],
  );

  useEffect(() => {
    document.title =
      !tabFocused && totalUnread > 0 ? `(${totalUnread}) ${PAGE_TITLE}` : PAGE_TITLE;
    return () => {
      document.title = PAGE_TITLE;
    };
  }, [totalUnread, tabFocused]);

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

  /** Nome do atendente atribuído (o contato só traz o id). */
  const assignedName = useCallback(
    (contact: Contact) =>
      contact.assigned_to != null
        ? (users.find((u) => u.id === contact.assigned_to)?.name ?? null)
        : null,
    [users],
  );

  /** A IA está de fato respondendo este contato?
   *
   *  Espelha o gating do backend (agent_should_handle): não basta
   *  `contact.ai_active` — o canal precisa estar com agent_enabled. Mostrar
   *  "IA ativa" só pelo flag do contato faria o painel mentir enquanto o canal
   *  está desligado, que é o estado de hoje em produção. */
  const aiActiveFor = useCallback(
    (contact: Contact) =>
      Boolean(
        contact.ai_active &&
          contact.channel_id != null &&
          agentStatus?.channels_enabled.includes(contact.channel_id),
      ),
    [agentStatus],
  );

  /** Assumir a conversa (ai_active=false) ou devolver para a IA.
   *
   *  O handler do agente relê ai_active a cada inbound, então o efeito é
   *  imediato: não precisa reiniciar nada nem esperar ciclo de worker. */
  const toggleAi = useCallback(
    async (contact: Contact, ativar: boolean) => {
      setTogglingAi(true);
      try {
        const atualizado = await inboxApi.patchContact(contact.id, {
          ai_active: ativar,
        });
        setContacts((cs) => cs.map((c) => (c.id === atualizado.id ? atualizado : c)));
        setSelected((s) => (s && s.id === atualizado.id ? atualizado : s));
        toast.success(
          ativar ? "Conversa devolvida para a IA." : "Você assumiu a conversa — a IA parou de responder.",
        );
      } catch (err) {
        toast.error(errMsg(err, "Falha ao alterar o atendimento por IA"));
      } finally {
        setTogglingAi(false);
      }
    },
    [],
  );

  // Filtro base (canal ativo + busca + status + filtros avançados).
  const baseFiltered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return contacts.filter((c) => {
      if (activeChannelId != null && c.channel_id !== activeChannelId) return false;
      if (statusFilter && c.lead_status !== statusFilter) return false;
      if (q) {
        const hay = `${c.name || ""} ${stripIg(c.wa_id)}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (
        filters.tagIds.length &&
        !(c.tags ?? []).some((t) => filters.tagIds.includes(t.id))
      )
        return false;
      if (filters.unreadOnly && !(c.unread > 0)) return false;
      if (filters.ai !== "all" && c.ai_active !== (filters.ai === "on")) return false;
      if (filters.sdr !== null && c.assigned_to !== filters.sdr) return false;
      return true;
    });
  }, [contacts, activeChannelId, statusFilter, search, filters]);

  const counts = useMemo(() => {
    let wpp = 0;
    let ig = 0;
    baseFiltered.forEach((c) => (kindOf(providerOf(c)) === "instagram" ? ig++ : wpp++));
    return { all: baseFiltered.length, whatsapp: wpp, instagram: ig };
  }, [baseFiltered, providerOf]);

  const visibleContacts = useMemo(
    () =>
      baseFiltered.filter(
        (c) =>
          (tab === "all" || kindOf(providerOf(c)) === tab) &&
          (!aiOnly || aiActiveFor(c)),
      ),
    [baseFiltered, tab, providerOf, aiOnly, aiActiveFor],
  );

  /** Quantas conversas a IA está atendendo agora (para o chip do filtro). */
  const aiCount = useMemo(
    () => baseFiltered.filter(aiActiveFor).length,
    [baseFiltered, aiActiveFor],
  );

  const statuses = useMemo(() => {
    const set = new Set<string>();
    contacts.forEach((c) => c.lead_status && set.add(c.lead_status));
    return Array.from(set);
  }, [contacts]);

  const openContact = useCallback((contact: Contact) => {
    setSelected(contact);
    setMessages([]);
    setShowScrollDown(false);
    loadMessages(contact);
    if (contact.unread > 0) {
      setContacts((cs) =>
        cs.map((x) => (x.id === contact.id ? { ...x, unread: 0 } : x)),
      );
      inboxApi.markRead(contact.id).catch(() => {});
    }
  }, [loadMessages]);

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

  /** Aplica um patch no contato aberto e na linha correspondente da lista. */
  const patchSelected = useCallback((patch: Partial<Contact>) => {
    setSelected((s) => (s ? { ...s, ...patch } : s));
    setContacts((cs) =>
      cs.map((c) => (selected && c.id === selected.id ? { ...c, ...patch } : c)),
    );
  }, [selected]);

  // Mudar etapa do lead a partir da conversa (mesma fonte: Contact.lead_status).
  const changeStage = async (status: string) => {
    if (!selected) return;
    const prev = selected.lead_status;
    patchSelected({ lead_status: status });
    try {
      await moveCard(selected.id, status);
    } catch {
      toast.error("Falha ao mudar etapa");
      patchSelected({ lead_status: prev });
    }
  };

  // Envio roteado por provider — comportamento preservado. Relança o erro para
  // que o composer possa piscar o ícone de falha.
  const sendText = async (text: string) => {
    if (!selected || !selected.channel_id) return;
    const ch = channelById.get(selected.channel_id);
    if (!ch) {
      toast.error("Canal do contato não encontrado");
      throw new Error("canal ausente");
    }
    if (ch.provider === "evolution" && !ch.instance_name) {
      toast.error("Canal sem instance_name");
      throw new Error("instance_name ausente");
    }
    try {
      if (ch.provider === "instagram") {
        const to = stripIg(selected.wa_id);
        await api.post(`/instagram/channels/${ch.id}/send-text`, { to, text });
      } else if (ch.provider === "official") {
        await api.post(`/meta/channels/${ch.id}/send-text`, { to: selected.wa_id, text });
      } else {
        await api.post("/evolution/send", null, {
          params: { instance_name: ch.instance_name, to: selected.wa_id, text },
        });
      }
      await loadMessages(selected, true);
      loadContacts();
    } catch (err) {
      toast.error(errMsg(err, "Falha ao enviar"));
      // Mesmo em falha, a mensagem é registrada no chat (status=failed):
      // recarrega para exibi-la.
      await loadMessages(selected, true);
      throw err;
    }
  };

  const afterMediaSend = useCallback(() => {
    if (selected) loadMessages(selected, true);
    loadContacts();
  }, [selected, loadMessages, loadContacts]);

  const onThreadScroll = () => {
    const el = threadRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollDown(dist > SCROLL_DOWN_THRESHOLD);
  };

  const activeChannel = activeChannelId != null ? channelById.get(activeChannelId) ?? null : null;
  const selectedChannel = channelOf(selected);

  /** Janela de atendimento de 24h.
   *
   *  Regra da Cloud API da Meta: passadas 24h do último inbound, só template
   *  aprovado passa. Vale SÓ para o canal oficial — Evolution e Instagram não
   *  têm essa janela, e avisar lá seria alarme falso.
   *
   *  Conta a partir das mensagens carregadas (não de `last_inbound_at` do
   *  contato) porque é o mesmo dado que a thread está exibindo. */
  const outOf24h = useMemo(() => {
    if (!selected || selectedChannel?.provider !== "official") return false;
    const ultimoInbound = [...messages]
      .reverse()
      .find((m) => m.direction === "inbound");
    if (!ultimoInbound?.timestamp) return false;
    try {
      const horas =
        (Date.now() - parseISO(ultimoInbound.timestamp).getTime()) / 3_600_000;
      return horas > 24;
    } catch {
      return false;
    }
  }, [selected, selectedChannel, messages]);
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
    // `wa-theme` redefine os tokens do shadcn só aqui dentro (ver globals.css):
    // a página inteira, incluindo os componentes shadcn, adota a paleta do
    // WhatsApp sem nenhum hex nos componentes.
    <div className="wa-theme -m-6 flex h-[calc(100vh-3.5rem)] flex-col bg-background text-foreground">
      {/* Banner global de sandbox: nesse modo o canal pode estar com o agente
          ligado e mesmo assim a IA não responder quase ninguém — sem o aviso,
          isso parece bug para quem está atendendo. */}
      {agentStatus?.sandbox && (
        <div className="flex shrink-0 items-center gap-2 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-[12px] text-amber-300">
          <FlaskConical className="h-4 w-4 shrink-0" />
          <span>
            <strong className="font-semibold">Agente em modo sandbox</strong> — a
            IA só responde {agentStatus.sandbox_count}{" "}
            {agentStatus.sandbox_count === 1 ? "contato de teste" : "contatos de teste"}.
            Os demais contatos não recebem resposta automática, mesmo com o canal
            habilitado.
          </span>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
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
            {/* wa-theme repetido: Radix renderiza em portal, fora da subárvore. */}
            <DropdownMenuContent align="start" className="wa-theme w-[320px]">
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

        {/* Busca + filtros + nova conversa */}
        <div className="flex items-center gap-2 border-b border-border p-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar conversa…"
              className="pl-8"
            />
          </div>
          <FiltersPopover
            filters={filters}
            onChange={setFilters}
            allTags={allTags}
            users={users}
          />
          <Button
            size="sm"
            className="h-9 shrink-0"
            onClick={() => setNewChatOpen(true)}
            aria-label="Nova conversa"
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>

        {/* Filtro de IA — só aparece se houver canal com o agente ligado. */}
        {(agentStatus?.channels_enabled.length ?? 0) > 0 && (
          <div className="flex items-center gap-1.5 border-b border-border px-2 py-2">
            <button
              onClick={() => setAiOnly((v) => !v)}
              className={cn(
                "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs transition-colors",
                aiOnly
                  ? "bg-accent text-accent-foreground"
                  : "bg-muted text-muted-foreground hover:bg-border",
              )}
            >
              <Sparkles className="h-3.5 w-3.5" />
              Atendidas pela IA
              <span className="opacity-80">({aiCount})</span>
            </button>
          </div>
        )}

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
              {countActiveFilters(filters) > 0 || search.trim()
                ? "Nenhuma conversa com esses filtros."
                : "Nenhuma conversa por aqui."}
            </div>
          ) : (
            visibleContacts.map((c) => {
              const name = c.name || stripIg(c.wa_id);
              const provider = providerOf(c);
              const unread = c.unread || 0;
              return (
                <button
                  key={c.id}
                  onClick={() => openContact(c)}
                  className={cn(
                    "flex w-full items-start gap-3 border-b border-border/60 px-3 py-3 text-left transition-colors hover:bg-muted",
                    selected?.id === c.id && "bg-border/70",
                  )}
                >
                  <div className="relative shrink-0">
                    <div
                      className={cn(
                        "flex h-[49px] w-[49px] items-center justify-center rounded-full text-sm font-semibold text-white",
                        avatarColor(name),
                      )}
                    >
                      {initialsOf(name)}
                    </div>
                    <span className="absolute -bottom-0.5 -right-0.5 rounded-full bg-card p-0.5">
                      <ChannelIcon provider={provider} size={14} />
                    </span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className={cn(
                          "truncate text-[15px]",
                          unread > 0 ? "font-semibold text-foreground" : "font-normal text-foreground",
                        )}
                      >
                        {name}
                      </span>
                      <span
                        className={cn(
                          "shrink-0 text-[11px]",
                          unread > 0 ? "text-accent" : "text-muted-foreground",
                        )}
                      >
                        {fmt(c.last_inbound_at)}
                      </span>
                    </div>
                    <div className="mt-0.5 flex items-center justify-between gap-2">
                      <span className="truncate text-[13px] text-muted-foreground">
                        {provider === "instagram" ? stripIg(c.wa_id) : formatPhone(c.wa_id)}
                      </span>
                      {unread > 0 && (
                        <span className="flex h-5 min-w-[20px] shrink-0 items-center justify-center rounded-full bg-accent px-1.5 text-[11px] font-bold leading-none text-accent-foreground">
                          {unread > 99 ? "99+" : unread}
                        </span>
                      )}
                    </div>
                    {((c.tags ?? []).length > 0 || assignedName(c)) && (
                      <div className="mt-1 flex flex-wrap items-center gap-1">
                        {(c.tags ?? []).slice(0, 3).map((t) => (
                          <span
                            key={t.id}
                            className={cn(
                              "rounded px-1.5 py-0.5 text-[10px] leading-none",
                              tagColorClasses[t.color] ?? tagColorClasses.blue,
                            )}
                          >
                            {t.name}
                          </span>
                        ))}
                        {(c.tags ?? []).length > 3 && (
                          <span className="text-[10px] text-muted-foreground">
                            +{c.tags.length - 3}
                          </span>
                        )}
                        {assignedName(c) && (
                          <span className="rounded bg-border px-1.5 py-0.5 text-[10px] leading-none text-muted-foreground">
                            @{assignedName(c)!.split(" ")[0]}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* ---------- Thread ---------- */}
      <div className={cn("min-w-0 flex-1 flex-col bg-background", selected ? "flex" : "hidden lg:flex")}>
        {!selected ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 bg-wa-empty text-muted-foreground">
            <div className="flex h-20 w-20 items-center justify-center rounded-full bg-border">
              <BrandWhatsApp size={40} />
            </div>
            <p className="text-[28px] font-light text-foreground">Conversas</p>
            <p className="text-sm">Selecione uma conversa para começar.</p>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="flex items-center gap-3 border-b border-border bg-secondary p-3">
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
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-semibold">
                    {selected.name || stripIg(selected.wa_id)}
                  </span>
                  {aiActiveFor(selected) && (
                    <span className="flex shrink-0 items-center gap-1 rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-medium text-accent">
                      <Sparkles className="h-3 w-3" />
                      IA ativa
                    </span>
                  )}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {providerOf(selected) === "instagram"
                    ? stripIg(selected.wa_id)
                    : formatPhone(selected.wa_id)}
                  {selected.lead_status ? ` · ${selected.lead_status}` : ""}
                </div>
              </div>

              {/* Assumir / devolver: só faz sentido em canal com o agente ligado. */}
              {selected.channel_id != null &&
                agentStatus?.channels_enabled.includes(selected.channel_id) && (
                  <Button
                    size="sm"
                    variant={selected.ai_active ? "secondary" : "default"}
                    disabled={togglingAi}
                    onClick={() => toggleAi(selected, !selected.ai_active)}
                    className="shrink-0 gap-1.5"
                    title={
                      selected.ai_active
                        ? "A IA para de responder e você assume o atendimento"
                        : "A IA volta a responder este contato"
                    }
                  >
                    {selected.ai_active ? (
                      <>
                        <UserCheck className="h-4 w-4" />
                        <span className="hidden sm:inline">Assumir conversa</span>
                      </>
                    ) : (
                      <>
                        <Bot className="h-4 w-4" />
                        <span className="hidden sm:inline">Devolver para IA</span>
                      </>
                    )}
                  </Button>
                )}

              <ChannelIcon provider={providerOf(selected)} size={28} />
              <Button
                size="icon"
                variant={crmOpen ? "secondary" : "ghost"}
                onClick={() => setCrmOpen((v) => !v)}
                aria-label="Detalhes do contato"
              >
                <PanelRight className="h-4 w-4" />
              </Button>
            </div>

            {/* Mensagens */}
            <div className="relative flex-1 overflow-hidden">
              <div
                ref={threadRef}
                onScroll={onThreadScroll}
                className="h-full space-y-1.5 overflow-auto p-4"
              >
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
                  groupByDay(messages).map((grupo) => (
                    <div key={grupo.day} className="space-y-1.5">
                      <div className="flex justify-center py-2">
                        <span className="rounded-lg bg-muted px-3 py-1.5 text-[12px] text-muted-foreground">
                          {grupo.day}
                        </span>
                      </div>
                      {grupo.items.map((m) => (
                        <div
                          key={m.id}
                          className={cn(
                            "flex",
                            m.direction === "outbound" ? "justify-end" : "justify-start",
                          )}
                        >
                          <div
                            className={cn(
                              "max-w-[70%] px-2.5 py-1.5 text-[14.2px] leading-[19px] shadow-sm",
                              m.direction === "outbound"
                                ? "rounded-lg rounded-tr-none bg-primary text-primary-foreground"
                                : "rounded-lg rounded-tl-none bg-wa-bubble-in text-foreground",
                            )}
                          >
                            <MessageContent m={m} />
                            <div
                              className={cn(
                                "mt-0.5 flex items-center justify-end gap-1 text-right text-[11px]",
                                m.direction === "outbound"
                                  ? "text-primary-foreground/60"
                                  : "text-muted-foreground",
                              )}
                            >
                              {m.sent_by_ai && (
                                <span
                                  className="mr-auto flex items-center gap-0.5 rounded bg-black/20 px-1 py-px text-[10px] font-medium"
                                  title="Enviada pelo agente de IA"
                                >
                                  <Bot className="h-3 w-3" />
                                  IA
                                </span>
                              )}
                              {fmtTime(m.timestamp)}
                              {m.direction === "outbound" && <MessageStatus status={m.status} />}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ))
                )}
                <div ref={bottomRef} />
              </div>

              {showScrollDown && (
                <Button
                  size="icon"
                  variant="secondary"
                  className="absolute bottom-4 right-4 rounded-full shadow-md"
                  onClick={() =>
                    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
                  }
                  aria-label="Ir para a última mensagem"
                >
                  <ChevronDown className="h-4 w-4" />
                </Button>
              )}
            </div>

            {outOf24h && (
              <div className="border-t border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300">
                Sem resposta do contato há mais de 24h — fora da janela de
                atendimento, a Meta pode rejeitar texto livre. Para reabrir a
                conversa, use um{" "}
                <button
                  type="button"
                  onClick={() => setTemplateOpen(true)}
                  className="font-medium underline underline-offset-2 hover:text-amber-200"
                >
                  template aprovado
                </button>
                .
              </div>
            )}

            <Composer
              contact={selected}
              channel={selectedChannel}
              onSendText={sendText}
              onAfterSend={afterMediaSend}
              onOpenTemplate={() => setTemplateOpen(true)}
            />
          </>
        )}
      </div>

      {/* ---------- Painel CRM ---------- */}
      {selected && crmOpen && (
        <CrmPanel
          contact={selected}
          stageColumns={stageColumns}
          allTags={allTags}
          users={users}
          onChangeStage={changeStage}
          onPatched={patchSelected}
          onTagsChanged={loadTags}
          onClose={() => setCrmOpen(false)}
        />
      )}
      </div>

      <NewChatDialog
        open={newChatOpen}
        onOpenChange={setNewChatOpen}
        channels={channels}
        onCreated={(contact, withTemplate) => {
          setContacts((cs) =>
            cs.some((c) => c.id === contact.id) ? cs : [contact, ...cs],
          );
          openContact(contact);
          if (withTemplate) setTemplateOpen(true);
        }}
      />

      {selected && selectedChannel?.provider === "official" && (
        <TemplateDialog
          open={templateOpen}
          onOpenChange={setTemplateOpen}
          channelId={selectedChannel.id}
          to={selected.wa_id}
          onSent={afterMediaSend}
        />
      )}
    </div>
  );
}
