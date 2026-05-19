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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { createMetaChannel, updateMetaChannel } from "@/lib/api-channels-meta";
import type { Channel, MetaChannelUpdate } from "@/types/api";

type OperationMode = "ai" | "chatbot" | "none";

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

export function MetaChannelDialog({ open, onOpenChange, channel, onSuccess }: Props) {
  const isEdit = Boolean(channel);

  const [name, setName] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [wabaId, setWabaId] = useState("");
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [operationMode, setOperationMode] = useState<OperationMode>("none");
  const [isActive, setIsActive] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (channel) {
      setName(channel.name);
      setPhoneNumber(channel.phone_number || "");
      setPhoneNumberId("");
      setWabaId("");
      setToken("");
      setOperationMode((channel.operation_mode as OperationMode) || "none");
      setIsActive(channel.is_active);
    } else {
      setName("");
      setPhoneNumber("");
      setPhoneNumberId("");
      setWabaId("");
      setToken("");
      setOperationMode("none");
      setIsActive(true);
    }
    setShowToken(false);
  }, [open, channel]);

  async function handleSave() {
    if (!name.trim()) {
      toast.error("Informe o nome");
      return;
    }
    if (!isEdit) {
      if (!phoneNumber.trim()) {
        toast.error("Informe o telefone");
        return;
      }
      if (!phoneNumberId.trim()) {
        toast.error("Informe o Phone Number ID");
        return;
      }
      if (!wabaId.trim()) {
        toast.error("Informe o WABA ID");
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
        const updates: MetaChannelUpdate = {
          name: name.trim(),
          operation_mode: operationMode,
          is_active: isActive,
        };
        if (token.trim()) {
          updates.whatsapp_token = token.trim();
        }
        await updateMetaChannel(channel.id, updates);
        toast.success("Canal atualizado");
      } else {
        await createMetaChannel({
          name: name.trim(),
          phone_number: phoneNumber.trim(),
          phone_number_id: phoneNumberId.trim(),
          waba_id: wabaId.trim(),
          whatsapp_token: token.trim(),
          operation_mode: operationMode,
        });
        toast.success("Canal Meta criado");
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
            {isEdit
              ? `Editar canal: ${channel?.name}`
              : "Adicionar canal WhatsApp Oficial (Meta)"}
          </DialogTitle>
        </DialogHeader>

        <div className="mt-2 space-y-4">
          <div className="space-y-1">
            <Label htmlFor="meta-name">Nome interno</Label>
            <Input
              id="meta-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ex: Cenat - Financeiro"
            />
          </div>

          {!isEdit && (
            <>
              <div className="space-y-1">
                <Label htmlFor="meta-phone">Telefone (display)</Label>
                <Input
                  id="meta-phone"
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  placeholder="+5511936235780"
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="meta-pnid">Phone Number ID</Label>
                <Input
                  id="meta-pnid"
                  value={phoneNumberId}
                  onChange={(e) => setPhoneNumberId(e.target.value)}
                  placeholder="1064349166769130"
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="meta-waba">WABA ID</Label>
                <Input
                  id="meta-waba"
                  value={wabaId}
                  onChange={(e) => setWabaId(e.target.value)}
                  placeholder="979635254656744"
                />
              </div>
            </>
          )}

          <div className="space-y-1">
            <Label htmlFor="meta-token">
              {isEdit ? "Rotacionar token (opcional)" : "Permanent Access Token"}
            </Label>
            <div className="flex gap-2">
              <Input
                id="meta-token"
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

          <div className="space-y-1">
            <Label>Modo de operação</Label>
            <Select
              value={operationMode}
              onValueChange={(v) => v && setOperationMode(v as OperationMode)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Sem automação</SelectItem>
                <SelectItem value="ai">IA</SelectItem>
                <SelectItem value="chatbot">Chatbot (fluxo)</SelectItem>
              </SelectContent>
            </Select>
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
