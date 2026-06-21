"use client";

import { useEffect, useState } from "react";
import axios from "axios";
import { Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { createInstagramChannel, updateInstagramChannel } from "@/lib/api-channels-instagram";
import type { Channel, InstagramChannelUpdate } from "@/types/api";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  channel?: Channel | null;
  onSuccess: () => void;
}

function errMsg(err: unknown, fallback = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fallback;
}

export function InstagramChannelDialog({ open, onOpenChange, channel, onSuccess }: Props) {
  const isEdit = Boolean(channel);

  const [name, setName] = useState("");
  const [instagramId, setInstagramId] = useState("");
  const [pageId, setPageId] = useState("");
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [isActive, setIsActive] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (channel) {
      setName(channel.name);
      setInstagramId(channel.instagram_id || "");
      setPageId(channel.page_id || "");
      setToken("");
      setIsActive(channel.is_active);
    } else {
      setName("");
      setInstagramId("");
      setPageId("");
      setToken("");
      setIsActive(true);
    }
    setShowToken(false);
  }, [open, channel]);

  async function handleSave() {
    if (!isEdit) {
      if (!instagramId.trim()) {
        toast.error("Informe o Instagram ID (conta profissional)");
        return;
      }
      if (!token.trim()) {
        toast.error("Informe o token de acesso");
        return;
      }
    }

    setSaving(true);
    try {
      if (isEdit && channel) {
        const updates: InstagramChannelUpdate = {
          name: name.trim() || channel.name,
          is_active: isActive,
        };
        if (token.trim()) {
          updates.access_token = token.trim();
        }
        await updateInstagramChannel(channel.id, updates);
        toast.success("Canal atualizado");
      } else {
        await createInstagramChannel({
          name: name.trim() || undefined,
          instagram_id: instagramId.trim(),
          page_id: pageId.trim() || undefined,
          access_token: token.trim(),
        });
        toast.success("Canal Instagram criado");
      }
      onSuccess();
      onOpenChange(false);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao salvar canal"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? `Editar canal: ${channel?.name}` : "Adicionar canal Instagram (Direct)"}
          </DialogTitle>
        </DialogHeader>

        <div className="mt-2 space-y-4">
          <div className="space-y-1">
            <Label htmlFor="ig-name">Nome interno</Label>
            <Input
              id="ig-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ex: @cenatsaudemental"
            />
          </div>

          {!isEdit && (
            <>
              <div className="space-y-1">
                <Label htmlFor="ig-id">Instagram ID (conta profissional)</Label>
                <Input
                  id="ig-id"
                  value={instagramId}
                  onChange={(e) => setInstagramId(e.target.value)}
                  placeholder="17841405925471370"
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="ig-page">Page ID (opcional)</Label>
                <Input
                  id="ig-page"
                  value={pageId}
                  onChange={(e) => setPageId(e.target.value)}
                  placeholder="709368575823331"
                />
              </div>
            </>
          )}

          <div className="space-y-1">
            <Label htmlFor="ig-token">
              {isEdit ? "Rotacionar token (opcional)" : "Page Access Token"}
            </Label>
            <div className="flex gap-2">
              <Input
                id="ig-token"
                type={showToken ? "text" : "password"}
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder={isEdit ? "Deixe em branco para manter o atual" : "EAAxxxxxxxx..."}
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={() => setShowToken((s) => !s)}
                aria-label={showToken ? "Esconder token" : "Mostrar token"}
              >
                {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
            {isEdit && (
              <p className="text-xs text-muted-foreground">
                Se preencher, o token atual será substituído. Token vazio mantém o existente.
              </p>
            )}
          </div>

          {isEdit && (
            <div className="flex items-center justify-between rounded-md border p-3">
              <div>
                <p className="text-sm font-medium">Canal ativo</p>
                <p className="text-xs text-muted-foreground">
                  Desativar não exclui, só pausa envios
                </p>
              </div>
              <Switch checked={isActive} onCheckedChange={setIsActive} />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Salvando..." : isEdit ? "Atualizar" : "Criar canal"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
