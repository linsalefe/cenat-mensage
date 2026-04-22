"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import axios from "axios";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";
import { ptBR } from "date-fns/locale";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowDownLeft,
  ArrowUpRight,
  MessageSquare,
  RefreshCw,
  Radio,
  Send,
  Users,
  Workflow,
} from "lucide-react";

import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface DashboardStats {
  generated_at: string;
  channels: {
    total: number;
    connected: number;
    by_mode: { ai: number; chatbot: number; none: number };
  };
  contacts: { total: number; new_24h: number; new_7d: number };
  messages: {
    total: number;
    last_24h: { inbound: number; outbound: number };
    last_7d: { inbound: number; outbound: number };
    series_7d: { day: string; inbound: number; outbound: number }[];
  };
  chatbot: {
    flows_total: number;
    flows_published: number;
    sessions_active: number;
    sessions_completed_24h: number;
  };
  broadcasts: {
    total: number;
    pending: number;
    running: number;
    completed_24h: number;
  };
}

function errMsg(err: unknown, fb = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fb;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get<DashboardStats>("/dashboard/stats");
      setStats(res.data);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao carregar dashboard"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !stats) {
    return <div className="text-sm text-muted-foreground">Carregando…</div>;
  }
  if (!stats) return null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Visão geral</h1>
          <p className="text-xs text-muted-foreground">
            Atualizado{" "}
            {(() => {
              try {
                return format(parseISO(stats.generated_at), "dd/MM/yy HH:mm:ss", {
                  locale: ptBR,
                });
              } catch {
                return stats.generated_at;
              }
            })()}
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={load}>
          <RefreshCw className="mr-1 h-3 w-3" /> Atualizar
        </Button>
      </div>

      {/* Primeira linha: 4 cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Canais</CardTitle>
            <Radio className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.channels.total}</div>
            <p className="text-xs text-muted-foreground">
              {stats.channels.connected} conectados de {stats.channels.total}
            </p>
            <div className="mt-2 flex flex-wrap gap-1">
              <Badge variant="outline">AI {stats.channels.by_mode.ai}</Badge>
              <Badge variant="outline">Chatbot {stats.channels.by_mode.chatbot}</Badge>
              <Badge variant="outline">None {stats.channels.by_mode.none}</Badge>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Contatos</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.contacts.total}</div>
            <p className="text-xs text-muted-foreground">
              +{stats.contacts.new_24h} nas últimas 24h
            </p>
            <p className="text-[11px] text-muted-foreground">
              +{stats.contacts.new_7d} nos últimos 7 dias
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Mensagens 24h</CardTitle>
            <MessageSquare className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {stats.messages.last_24h.inbound + stats.messages.last_24h.outbound}
            </div>
            <div className="mt-2 flex gap-3 text-xs">
              <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                <ArrowDownLeft className="h-3 w-3" /> {stats.messages.last_24h.inbound}
              </span>
              <span className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400">
                <ArrowUpRight className="h-3 w-3" /> {stats.messages.last_24h.outbound}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Broadcasts</CardTitle>
            <Send className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.broadcasts.total}</div>
            <div className="mt-2 flex flex-wrap gap-1 text-[11px]">
              <Badge variant="outline">Pendentes {stats.broadcasts.pending}</Badge>
              <Badge variant="outline">Rodando {stats.broadcasts.running}</Badge>
              <Badge variant="outline">
                Concluídos 24h {stats.broadcasts.completed_24h}
              </Badge>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Segunda linha: 2 cards */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Chatbot</CardTitle>
            <Workflow className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Fluxos publicados</span>
              <span className="font-medium">
                {stats.chatbot.flows_published} / {stats.chatbot.flows_total}
              </span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Sessões ativas</span>
              <span className="font-medium">{stats.chatbot.sessions_active}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Concluídas 24h</span>
              <span className="font-medium">{stats.chatbot.sessions_completed_24h}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Últimos 7 dias — Mensagens</CardTitle>
          </CardHeader>
          <CardContent className="h-56">
            {stats.messages.series_7d.length === 0 ? (
              <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                Sem mensagens nos últimos 7 dias.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={stats.messages.series_7d.map((p) => ({
                    day: p.day?.slice(5) ?? "",
                    inbound: p.inbound,
                    outbound: p.outbound,
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                  <XAxis dataKey="day" fontSize={11} />
                  <YAxis fontSize={11} allowDecimals={false} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="inbound" stackId="m" fill="#10b981" name="Recebidas" />
                  <Bar dataKey="outbound" stackId="m" fill="#3b82f6" name="Enviadas" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="flex gap-4 text-xs text-muted-foreground">
        <Link href="/broadcasts" className="hover:underline">
          Ver todos os broadcasts →
        </Link>
        <Link href="/canais" className="hover:underline">
          Ver canais →
        </Link>
      </div>
    </div>
  );
}
