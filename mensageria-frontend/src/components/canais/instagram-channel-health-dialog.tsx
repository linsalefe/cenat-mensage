"use client";

import { useEffect, useState } from "react";
import axios from "axios";
import { BrandInstagram } from "@/components/brand/channel-icon";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getInstagramHealth } from "@/lib/api-channels-instagram";
import type { Channel, InstagramChannelHealth } from "@/types/api";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  channel: Channel | null;
}

function errStr(err: unknown): string {
  if (axios.isAxiosError(err) && err.response?.data?.detail) {
    return String(err.response.data.detail);
  }
  return typeof err === "string" ? err : JSON.stringify(err);
}

export function InstagramChannelHealthDialog({ open, onOpenChange, channel }: Props) {
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<InstagramChannelHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !channel) return;
    let cancelled = false;
    setLoading(true);
    setHealth(null);
    setError(null);
    getInstagramHealth(channel.id)
      .then((h) => {
        if (!cancelled) setHealth(h);
      })
      .catch((err) => {
        if (!cancelled) setError(errStr(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, channel]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <BrandInstagram size={16} /> Saúde do canal — {channel?.name}
          </DialogTitle>
        </DialogHeader>

        <div className="mt-2 min-h-[80px] space-y-3 text-sm">
          {loading && <p className="text-muted-foreground">Consultando a Graph API…</p>}

          {!loading && error && (
            <div className="rounded bg-red-500/10 p-3 text-red-600 dark:text-red-400">
              <p className="font-medium">Erro ao consultar</p>
              <p className="mt-1 break-words font-mono text-xs">{error}</p>
            </div>
          )}

          {!loading && health && health.ok && (
            <div className="flex items-center gap-3 rounded-md border p-3">
              {health.profile_picture_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={health.profile_picture_url}
                  alt={health.username || "perfil"}
                  className="h-12 w-12 rounded-full object-cover"
                />
              ) : (
                <BrandInstagram size={40} />
              )}
              <div>
                <p className="font-medium">@{health.username || "—"}</p>
                <p className="text-xs text-muted-foreground">{health.name || ""}</p>
                <p className="mt-1 inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" /> token válido
                </p>
              </div>
            </div>
          )}

          {!loading && health && !health.ok && (
            <div className="rounded bg-amber-500/10 p-3 text-amber-700 dark:text-amber-400">
              <p className="font-medium">Token não alcançou a conta</p>
              <p className="mt-1 break-words font-mono text-xs">
                {typeof health.error === "string" ? health.error : JSON.stringify(health.error)}
              </p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Fechar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
