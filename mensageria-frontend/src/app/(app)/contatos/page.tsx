"use client";

import { useCallback, useEffect, useState } from "react";
import { format, parseISO } from "date-fns";
import { ptBR } from "date-fns/locale";
import axios from "axios";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import type { Contact, Message } from "@/types/api";

interface ContactList {
  total: number;
  limit: number;
  offset: number;
  items: Contact[];
}

function errMsg(err: unknown, fallback = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fallback;
}

function fmt(dateStr: string | null) {
  if (!dateStr) return "—";
  try {
    return format(parseISO(dateStr), "dd/MM/yy HH:mm", { locale: ptBR });
  } catch {
    return dateStr;
  }
}

const PAGE = 30;

export default function ContatosPage() {
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<ContactList | null>(null);
  const [loading, setLoading] = useState(true);

  const [selected, setSelected] = useState<Contact | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get<ContactList>("/contacts", {
        params: { search: search || undefined, limit: PAGE, offset },
      });
      setData(res.data);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao carregar contatos"));
    } finally {
      setLoading(false);
    }
  }, [search, offset]);

  useEffect(() => {
    load();
  }, [load]);

  const openContact = async (contact: Contact) => {
    setSelected(contact);
    try {
      const res = await api.get<Message[]>(`/contacts/${contact.id}/messages`, {
        params: { limit: 20 },
      });
      setMessages(res.data);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao carregar mensagens"));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="mb-1 text-2xl font-semibold tracking-tight">Contatos</h1>
          <p className="text-sm text-muted-foreground">
            Contatos que já interagiram pelos canais.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Input
            placeholder="Buscar por nome ou número…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
            className="w-64"
          />
        </div>
      </div>

      <div className="text-xs text-muted-foreground">
        {data ? `${data.total} contato(s)` : ""}
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>WA ID</TableHead>
            <TableHead>Nome</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Canal</TableHead>
            <TableHead>Último inbound</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                Carregando…
              </TableCell>
            </TableRow>
          ) : !data || data.items.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                Sem contatos.
              </TableCell>
            </TableRow>
          ) : (
            data.items.map((c) => (
              <TableRow
                key={c.id}
                className="cursor-pointer"
                onClick={() => openContact(c)}
              >
                <TableCell className="font-mono text-xs">{c.wa_id}</TableCell>
                <TableCell>
                  {c.name || "—"}
                  {c.is_group && <Badge variant="outline" className="ml-2">grupo</Badge>}
                </TableCell>
                <TableCell>{c.lead_status || "—"}</TableCell>
                <TableCell>{c.channel_name || "—"}</TableCell>
                <TableCell>{fmt(c.last_inbound_at)}</TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      {data && data.total > PAGE && (
        <div className="flex items-center justify-between">
          <Button
            variant="outline"
            size="sm"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE))}
          >
            Anterior
          </Button>
          <span className="text-xs text-muted-foreground">
            {offset + 1}–{Math.min(offset + PAGE, data.total)} de {data.total}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={offset + PAGE >= data.total}
            onClick={() => setOffset(offset + PAGE)}
          >
            Próximo
          </Button>
        </div>
      )}

      <Dialog open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {selected?.name || selected?.wa_id}
              <div className="font-mono text-xs font-normal text-muted-foreground">
                {selected?.wa_id}
              </div>
            </DialogTitle>
          </DialogHeader>
          <div className="max-h-96 space-y-2 overflow-auto">
            {messages.length === 0 ? (
              <div className="text-center text-sm text-muted-foreground">
                Sem mensagens.
              </div>
            ) : (
              messages.map((m) => (
                <div
                  key={m.id}
                  className={`rounded px-3 py-2 text-sm ${
                    m.direction === "outbound"
                      ? "ml-8 bg-primary/10"
                      : "mr-8 bg-muted"
                  }`}
                >
                  <div className="text-xs text-muted-foreground">
                    {m.direction === "outbound" ? "→" : "←"} {fmt(m.timestamp)}
                    {m.sender_name ? ` — ${m.sender_name}` : ""}
                  </div>
                  <div className="whitespace-pre-wrap">{m.content || `[${m.message_type}]`}</div>
                </div>
              ))
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
