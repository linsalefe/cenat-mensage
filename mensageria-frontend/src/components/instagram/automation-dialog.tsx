"use client";

import { useEffect, useMemo, useState } from "react";
import axios from "axios";
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
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { createAutomation, updateAutomation } from "@/lib/api-instagram-automations";
import type {
  IgActionType,
  IgMatchMode,
  IgTriggerType,
  InstagramAutomation,
} from "@/types/api";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  channelId: number;
  automation?: InstagramAutomation | null;
  onSuccess: () => void;
}

function errMsg(err: unknown, fallback = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fallback;
}

const TRIGGER_LABELS: Record<IgTriggerType, string> = {
  comment: "Comentário",
  dm_received: "DM recebida",
  reaction: "Reação",
  postback: "Ice breaker (postback)",
  mention: "Menção",
  story_reply: "Resposta a story",
};

const ACTION_LABELS: Record<IgActionType, string> = {
  send_dm: "Enviar DM",
  private_reply: "Responder no direct (private reply)",
  public_comment_reply: "Responder no comentário",
};

// Quais ações fazem sentido por gatilho (o resto fica desabilitado com tooltip).
const ALLOWED_ACTIONS: Record<IgTriggerType, IgActionType[]> = {
  comment: ["private_reply", "public_comment_reply"],
  mention: ["private_reply", "public_comment_reply"],
  reaction: ["send_dm"],
  postback: ["send_dm"],
  dm_received: ["send_dm"],
  story_reply: ["send_dm"],
};

const ALL_ACTIONS: IgActionType[] = ["send_dm", "private_reply", "public_comment_reply"];
const TEXT_TRIGGERS: IgTriggerType[] = ["comment", "dm_received", "story_reply"];

export function AutomationDialog({ open, onOpenChange, channelId, automation, onSuccess }: Props) {
  const isEdit = Boolean(automation);

  const [name, setName] = useState("");
  const [triggerType, setTriggerType] = useState<IgTriggerType>("comment");
  const [actionType, setActionType] = useState<IgActionType>("private_reply");
  const [keywords, setKeywords] = useState("");
  const [match, setMatch] = useState<IgMatchMode>("any");
  const [mediaId, setMediaId] = useState("");
  const [emoji, setEmoji] = useState("");
  const [payload, setPayload] = useState("");
  const [text, setText] = useState("");
  const [oncePerContact, setOncePerContact] = useState(true);
  const [priority, setPriority] = useState(100);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (automation) {
      const tc = automation.trigger_config || {};
      setName(automation.name);
      setTriggerType(automation.trigger_type);
      setActionType(automation.action_type);
      setKeywords((tc.keywords || []).join(", "));
      setMatch(tc.match || "any");
      setMediaId(tc.media_id || "");
      setEmoji(tc.emoji || "");
      setPayload(tc.payload || "");
      setText(automation.action_config?.text || "");
      setOncePerContact(automation.once_per_contact);
      setPriority(automation.priority);
    } else {
      setName("");
      setTriggerType("comment");
      setActionType("private_reply");
      setKeywords("");
      setMatch("any");
      setMediaId("");
      setEmoji("");
      setPayload("");
      setText("");
      setOncePerContact(true);
      setPriority(100);
    }
  }, [open, automation]);

  const allowed = ALLOWED_ACTIONS[triggerType];

  // Se a ação atual não é válida pro gatilho, cai pra primeira válida.
  useEffect(() => {
    if (!allowed.includes(actionType)) {
      setActionType(allowed[0]);
    }
  }, [triggerType]); // eslint-disable-line react-hooks/exhaustive-deps

  const isTextTrigger = TEXT_TRIGGERS.includes(triggerType);

  const buildTriggerConfig = useMemo(
    () => () => {
      if (isTextTrigger) {
        const kws = keywords
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean);
        const cfg: Record<string, unknown> = { keywords: kws, match };
        if (triggerType === "comment" && mediaId.trim()) cfg.media_id = mediaId.trim();
        return cfg;
      }
      if (triggerType === "reaction") return emoji.trim() ? { emoji: emoji.trim() } : {};
      if (triggerType === "postback") return payload.trim() ? { payload: payload.trim() } : {};
      return {};
    },
    [isTextTrigger, keywords, match, mediaId, emoji, payload, triggerType],
  );

  async function handleSave() {
    if (!name.trim()) {
      toast.error("Informe o nome da automação");
      return;
    }
    if (!text.trim()) {
      toast.error("Informe o texto da resposta");
      return;
    }
    setSaving(true);
    try {
      const body = {
        name: name.trim(),
        trigger_type: triggerType,
        trigger_config: buildTriggerConfig(),
        action_type: actionType,
        action_config: { text: text.trim() },
        once_per_contact: oncePerContact,
        priority,
      };
      if (isEdit && automation) {
        await updateAutomation(automation.id, body);
        toast.success("Automação atualizada");
      } else {
        await createAutomation(channelId, body);
        toast.success("Automação criada");
      }
      onSuccess();
      onOpenChange(false);
    } catch (err) {
      toast.error(errMsg(err, "Falha ao salvar automação"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Editar automação" : "Nova automação"}</DialogTitle>
        </DialogHeader>

        <div className="mt-2 space-y-4">
          <div className="space-y-1">
            <Label htmlFor="auto-name">Nome</Label>
            <Input
              id="auto-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ex: Comentou preço → direct"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Gatilho</Label>
              <Select value={triggerType} onValueChange={(v) => setTriggerType(v as IgTriggerType)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(TRIGGER_LABELS) as IgTriggerType[]).map((t) => (
                    <SelectItem key={t} value={t}>
                      {TRIGGER_LABELS[t]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label>Ação</Label>
              <Select value={actionType} onValueChange={(v) => setActionType(v as IgActionType)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <TooltipProvider>
                    {ALL_ACTIONS.map((a) => {
                      const ok = allowed.includes(a);
                      return (
                        <Tooltip key={a}>
                          <TooltipTrigger asChild>
                            <div>
                              <SelectItem value={a} disabled={!ok}>
                                {ACTION_LABELS[a]}
                              </SelectItem>
                            </div>
                          </TooltipTrigger>
                          {!ok && (
                            <TooltipContent side="right">
                              Não disponível para o gatilho “{TRIGGER_LABELS[triggerType]}”
                            </TooltipContent>
                          )}
                        </Tooltip>
                      );
                    })}
                  </TooltipProvider>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Condição — condicional ao gatilho */}
          {isTextTrigger && (
            <div className="space-y-3 rounded-md border p-3">
              <div className="space-y-1">
                <Label htmlFor="auto-keywords">Palavras-chave (separe por vírgula)</Label>
                <Input
                  id="auto-keywords"
                  value={keywords}
                  onChange={(e) => setKeywords(e.target.value)}
                  placeholder="preço, valor, quanto custa"
                />
                <p className="text-xs text-muted-foreground">
                  Vazio = qualquer mensagem dispara.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Correspondência</Label>
                  <Select value={match} onValueChange={(v) => setMatch(v as IgMatchMode)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="any">Qualquer (any)</SelectItem>
                      <SelectItem value="all">Todas (all)</SelectItem>
                      <SelectItem value="exact">Exata (exact)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {triggerType === "comment" && (
                  <div className="space-y-1">
                    <Label htmlFor="auto-media">Media ID (opcional)</Label>
                    <Input
                      id="auto-media"
                      value={mediaId}
                      onChange={(e) => setMediaId(e.target.value)}
                      placeholder="restringe a 1 post"
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          {triggerType === "reaction" && (
            <div className="space-y-1 rounded-md border p-3">
              <Label htmlFor="auto-emoji">Emoji (opcional)</Label>
              <Input
                id="auto-emoji"
                value={emoji}
                onChange={(e) => setEmoji(e.target.value)}
                placeholder="❤️ — vazio = qualquer reação"
              />
            </div>
          )}

          {triggerType === "postback" && (
            <div className="space-y-1 rounded-md border p-3">
              <Label htmlFor="auto-payload">Payload do botão</Label>
              <Input
                id="auto-payload"
                value={payload}
                onChange={(e) => setPayload(e.target.value)}
                placeholder="BTN_PRECO"
              />
            </div>
          )}

          {triggerType === "mention" && (
            <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
              Menções disparam sem ler o texto nesta versão — qualquer menção aciona a ação.
            </p>
          )}

          <div className="space-y-1">
            <Label htmlFor="auto-text">Texto da resposta</Label>
            <Textarea
              id="auto-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={3}
              placeholder="Oi {username}! Te respondo no direct 👋"
            />
            <p className="text-xs text-muted-foreground">
              <code>{"{username}"}</code> é substituído pelo @ de quem disparou (quando disponível).
            </p>
          </div>

          <div className="flex items-center justify-between rounded-md border p-3">
            <div>
              <p className="text-sm font-medium">Uma vez por contato</p>
              <p className="text-xs text-muted-foreground">
                Não dispara 2x pro mesmo gatilho/contato
              </p>
            </div>
            <Switch checked={oncePerContact} onCheckedChange={setOncePerContact} />
          </div>

          <div className="space-y-1">
            <Label htmlFor="auto-priority">Prioridade (menor avalia antes)</Label>
            <Input
              id="auto-priority"
              type="number"
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value) || 0)}
              className="w-32"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Salvando..." : isEdit ? "Atualizar" : "Criar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
