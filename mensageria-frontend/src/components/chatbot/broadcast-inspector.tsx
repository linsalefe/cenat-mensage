'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Upload, Search, RefreshCw, X as XIcon } from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';
import { type Node } from '@xyflow/react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';
import { contactListsApi } from '@/lib/api-contact-lists';
import { fetchGroups, invalidateGroupCache } from '@/lib/api-groups';
import { mediaApi } from '@/lib/api-media';
import { templatesApi } from '@/lib/api-templates';
import type {
  BroadcastTemplateParam,
  BroadcastTemplateParamType,
  Channel,
  ContactList,
  EvolutionGroup,
  MediaAsset,
  MetaTemplate,
} from '@/types/api';

function errMsg(err: unknown, fallback = 'Erro inesperado') {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fallback;
}

interface InspectorProps {
  node: Node;
  onChange: (data: Record<string, unknown>) => void;
  channels: Channel[];
  flowChannelId?: number | null;
}

export function BroadcastInspector({
  node,
  onChange,
  channels,
  flowChannelId = null,
}: InspectorProps) {
  const type = node.type;
  const data = (node.data || {}) as Record<string, any>;

  const update = (patch: Record<string, unknown>) => onChange({ ...data, ...patch });

  if (type === 'trigger_schedule') {
    return <TriggerScheduleInspector data={data} update={update} />;
  }
  if (type === 'audience') {
    return <AudienceInspector data={data} update={update} channels={channels} />;
  }
  if (type === 'message_media') {
    return <MessageMediaInspector data={data} update={update} />;
  }
  if (type === 'template_send') {
    return <TemplateSendInspector data={data} update={update} channelId={flowChannelId} />;
  }
  if (type === 'broadcast_send') {
    return <BroadcastSendInspector data={data} update={update} />;
  }
  return (
    <div className="p-4 text-sm text-muted-foreground">
      Este nó não tem configuração.
    </div>
  );
}

// ------------------------------------------------------------
// Trigger Schedule
// ------------------------------------------------------------
function TriggerScheduleInspector({
  data,
  update,
}: {
  data: Record<string, any>;
  update: (patch: Record<string, unknown>) => void;
}) {
  return (
    <div className="space-y-4 p-4">
      <div className="space-y-2">
        <Label>Modo</Label>
        <Select
          value={data.mode || 'once'}
          onValueChange={(v) => update({ mode: v })}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="once">Uma vez</SelectItem>
            <SelectItem value="recurrent" disabled>
              Recorrente (em breve)
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2">
        <Switch
          checked={!!data.run_immediately}
          onCheckedChange={(v) => update({ run_immediately: v })}
        />
        <Label className="cursor-pointer">Executar imediatamente ao salvar</Label>
      </div>

      {!data.run_immediately && (
        <div className="space-y-2">
          <Label>Data e hora (America/Sao_Paulo)</Label>
          <Input
            type="datetime-local"
            value={data.scheduled_at || ''}
            onChange={(e) => update({ scheduled_at: e.target.value })}
          />
          <p className="text-[11px] text-muted-foreground">
            Fuso fixo: America/Sao_Paulo (UTC-3).
          </p>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------
// Audience
// ------------------------------------------------------------
function AudienceInspector({
  data,
  update,
  channels,
}: {
  data: Record<string, any>;
  update: (patch: Record<string, unknown>) => void;
  channels: Channel[];
}) {
  const channel = useMemo(
    () => channels.find((c) => c.id === data.channel_id) || null,
    [channels, data.channel_id],
  );

  const [groups, setGroups] = useState<EvolutionGroup[]>([]);
  const [loadingGroups, setLoadingGroups] = useState(false);
  const [groupSearch, setGroupSearch] = useState('');
  const [lists, setLists] = useState<ContactList[]>([]);

  useEffect(() => {
    contactListsApi
      .list()
      .then(setLists)
      .catch(() => undefined);
  }, []);

  const selectedGroupIds: string[] = Array.isArray(data.audience_spec?.group_ids)
    ? data.audience_spec.group_ids
    : [];

  const loadGroups = useCallback(
    async (force = false) => {
      if (!channel?.instance_name) return;
      if (force) invalidateGroupCache(channel.instance_name);
      setLoadingGroups(true);
      try {
        const res = await fetchGroups(channel.instance_name);
        setGroups(res);
      } catch (err) {
        toast.error(errMsg(err, 'Falha ao buscar grupos'));
      } finally {
        setLoadingGroups(false);
      }
    },
    [channel],
  );

  useEffect(() => {
    if (data.audience_type === 'selected_groups' && channel?.instance_name) {
      loadGroups(false);
    }
  }, [data.audience_type, channel, loadGroups]);

  const toggleGroup = (id: string) => {
    const set = new Set(selectedGroupIds);
    if (set.has(id)) set.delete(id);
    else set.add(id);
    update({ audience_spec: { ...(data.audience_spec || {}), group_ids: Array.from(set) } });
  };

  const selectAll = () =>
    update({
      audience_spec: {
        ...(data.audience_spec || {}),
        group_ids: filteredGroups.map((g) => g.id),
      },
    });

  const selectNone = () =>
    update({ audience_spec: { ...(data.audience_spec || {}), group_ids: [] } });

  const filteredGroups = useMemo(() => {
    const q = groupSearch.trim().toLowerCase();
    if (!q) return groups;
    return groups.filter((g) => (g.subject || '').toLowerCase().includes(q));
  }, [groups, groupSearch]);

  return (
    <div className="space-y-4 p-4">
      <div className="space-y-2">
        <Label>Canal (instância)</Label>
        <Select
          value={data.channel_id ? String(data.channel_id) : ''}
          onValueChange={(v) => update({ channel_id: Number(v) })}
        >
          <SelectTrigger>
            <SelectValue placeholder="Escolha o canal…" />
          </SelectTrigger>
          <SelectContent>
            {channels.map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>
                {c.name} ({c.instance_name || '—'})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label>Tipo de audiência</Label>
        <Select
          value={data.audience_type || 'selected_groups'}
          onValueChange={(v) =>
            update({ audience_type: v, audience_spec: {} })
          }
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all_groups">Todos os grupos da instância</SelectItem>
            <SelectItem value="selected_groups">Grupos selecionados</SelectItem>
            <SelectItem value="contacts_tag" disabled>
              Contatos por tag (em breve)
            </SelectItem>
            <SelectItem value="csv">Lista de contatos</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {data.audience_type === 'csv' && (
        <div className="space-y-2">
          <Label>Lista de contatos</Label>
          <Select
            value={data.audience_spec?.list_id ? String(data.audience_spec.list_id) : ''}
            onValueChange={(v) => update({ audience_spec: { list_id: Number(v) } })}
          >
            <SelectTrigger>
              <SelectValue placeholder="Selecione uma lista" />
            </SelectTrigger>
            <SelectContent>
              {lists.length === 0 ? (
                <SelectItem value="__empty" disabled>
                  Nenhuma lista cadastrada
                </SelectItem>
              ) : (
                lists.map((l) => (
                  <SelectItem key={l.id} value={String(l.id)}>
                    {l.name} ({l.member_count} contatos)
                  </SelectItem>
                ))
              )}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Crie e gerencie listas em{' '}
            <a href="/listas" className="underline">
              Listas
            </a>
            .
          </p>
        </div>
      )}

      {data.audience_type === 'selected_groups' && channel && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>Grupos ({selectedGroupIds.length} selecionados)</Label>
            <Button size="sm" variant="ghost" onClick={() => loadGroups(true)}>
              <RefreshCw className="h-3 w-3" />
            </Button>
          </div>
          <div className="relative">
            <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="pl-7"
              placeholder="Buscar grupo…"
              value={groupSearch}
              onChange={(e) => setGroupSearch(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={selectAll} disabled={loadingGroups}>
              Selecionar todos
            </Button>
            <Button size="sm" variant="outline" onClick={selectNone} disabled={loadingGroups}>
              Desmarcar todos
            </Button>
          </div>
          <div className="max-h-64 space-y-1 overflow-auto rounded border p-2">
            {loadingGroups ? (
              <div className="p-2 text-center text-xs text-muted-foreground">Carregando…</div>
            ) : filteredGroups.length === 0 ? (
              <div className="p-2 text-center text-xs text-muted-foreground">
                Nenhum grupo encontrado.
              </div>
            ) : (
              filteredGroups.map((g) => {
                const checked = selectedGroupIds.includes(g.id);
                return (
                  <label
                    key={g.id}
                    className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-xs hover:bg-muted"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleGroup(g.id)}
                    />
                    <span className="flex-1 truncate">{g.subject || '(sem título)'}</span>
                    {g.size != null && (
                      <span className="text-muted-foreground">{g.size}</span>
                    )}
                  </label>
                );
              })
            )}
          </div>
        </div>
      )}

      {data.audience_type === 'all_groups' && channel && (
        <p className="text-xs text-muted-foreground">
          Todos os grupos ativos da instância <code>{channel.instance_name}</code>{' '}
          serão alvos. A lista é resolvida no momento do envio.
        </p>
      )}
    </div>
  );
}

// ------------------------------------------------------------
// Message + Media
// ------------------------------------------------------------
function MessageMediaInspector({
  data,
  update,
}: {
  data: Record<string, any>;
  update: (patch: Record<string, unknown>) => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [library, setLibrary] = useState<MediaAsset[]>([]);
  const [loadingLib, setLoadingLib] = useState(false);

  const onFile = async (file: File) => {
    setUploading(true);
    try {
      const asset = await mediaApi.upload(file);
      update({
        media_id: asset.id,
        media_url: asset.url,
        media_type: asset.media_type,
      });
      toast.success('Mídia enviada');
    } catch (err) {
      toast.error(errMsg(err, 'Falha no upload'));
    } finally {
      setUploading(false);
    }
  };

  const openLibrary = async () => {
    setLibraryOpen(true);
    setLoadingLib(true);
    try {
      const list = await mediaApi.list();
      setLibrary(list);
    } catch (err) {
      toast.error(errMsg(err));
    } finally {
      setLoadingLib(false);
    }
  };

  const pickFromLibrary = (asset: MediaAsset) => {
    update({ media_id: asset.id, media_url: asset.url, media_type: asset.media_type });
    setLibraryOpen(false);
  };

  const clearMedia = () =>
    update({ media_id: null, media_url: null, media_type: null });

  return (
    <div className="space-y-4 p-4">
      <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-400">
        ⚠️ Mensagem livre só dispara para contatos que enviaram alguma mensagem nas últimas 24h. Para disparo proativo de campanha, use &quot;Template oficial&quot;.
      </div>

      <div className="space-y-2">
        <Label>Texto (aceita variáveis: {'{nome}'}, {'{grupo_nome}'})</Label>
        <Textarea
          value={data.text || ''}
          onChange={(e) => update({ text: e.target.value })}
          rows={4}
          placeholder="Olá {nome}! Nova atualização…"
        />
      </div>

      <div className="space-y-2">
        <Label>Mídia (opcional)</Label>
        {data.media_id ? (
          <div className="flex items-center justify-between rounded border p-2">
            <div className="text-xs">
              <Badge variant="secondary">{data.media_type}</Badge>{' '}
              <span className="font-mono">#{data.media_id}</span>
            </div>
            <Button size="sm" variant="ghost" onClick={clearMedia}>
              <XIcon className="h-3 w-3" />
            </Button>
          </div>
        ) : (
          <div className="flex gap-2">
            <label className="flex flex-1 cursor-pointer items-center justify-center gap-2 rounded border border-dashed px-3 py-4 text-xs hover:bg-muted">
              <Upload className="h-3 w-3" />
              {uploading ? 'Enviando…' : 'Enviar arquivo'}
              <input
                type="file"
                className="hidden"
                accept="image/jpeg,image/png,image/webp,audio/ogg,audio/mpeg,video/mp4,application/pdf"
                disabled={uploading}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) onFile(f);
                }}
              />
            </label>
            <Button size="sm" variant="outline" onClick={openLibrary}>
              Biblioteca
            </Button>
          </div>
        )}
      </div>

      {(data.media_type === 'image' || data.media_type === 'video') && (
        <div className="space-y-2">
          <Label>Legenda (opcional)</Label>
          <Input
            value={data.caption || ''}
            onChange={(e) => update({ caption: e.target.value })}
          />
        </div>
      )}

      {libraryOpen && (
        <div className="rounded border p-2">
          <div className="mb-2 flex items-center justify-between">
            <Label>Biblioteca</Label>
            <Button size="sm" variant="ghost" onClick={() => setLibraryOpen(false)}>
              <XIcon className="h-3 w-3" />
            </Button>
          </div>
          {loadingLib ? (
            <div className="p-2 text-center text-xs text-muted-foreground">Carregando…</div>
          ) : library.length === 0 ? (
            <div className="p-2 text-center text-xs text-muted-foreground">
              Nenhum arquivo ainda.
            </div>
          ) : (
            <div className="max-h-48 space-y-1 overflow-auto">
              {library.map((a) => (
                <button
                  key={a.id}
                  className="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs hover:bg-muted"
                  onClick={() => pickFromLibrary(a)}
                >
                  <Badge variant="outline">{a.media_type}</Badge>
                  <span className="flex-1 truncate">{a.filename}</span>
                  <span className="text-muted-foreground">
                    {(a.size_bytes / 1024).toFixed(1)}k
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------
// Broadcast Send
// ------------------------------------------------------------
function BroadcastSendInspector({
  data,
  update,
}: {
  data: Record<string, any>;
  update: (patch: Record<string, unknown>) => void;
}) {
  return (
    <div className="space-y-4 p-4">
      <div className="space-y-2">
        <Label>Nome do disparo</Label>
        <Input
          value={data.name || ''}
          onChange={(e) => update({ name: e.target.value })}
          placeholder="Ex: Aviso semanal 22/abr"
        />
      </div>

      <div className="space-y-2">
        <Label>
          Intervalo entre envios:{' '}
          <span className="font-mono">{data.interval_seconds ?? 5}s</span>
        </Label>
        <input
          type="range"
          min={1}
          max={300}
          value={data.interval_seconds ?? 5}
          onChange={(e) => update({ interval_seconds: Number(e.target.value) })}
          className="w-full"
        />
        <p className="text-[11px] text-muted-foreground">
          Anti-ban: recomendado 5-15s. Entre 1 e 300.
        </p>
      </div>

      <div className="flex items-center gap-2">
        <Switch
          checked={!!data.activate_on_publish}
          onCheckedChange={(v) => update({ activate_on_publish: v })}
        />
        <Label className="cursor-pointer">Criar job ao publicar</Label>
      </div>
    </div>
  );
}

// ------------------------------------------------------------
// Template Send (Fase 4.9)
// ------------------------------------------------------------
function TemplateSendInspector({
  data,
  update,
  channelId,
}: {
  data: Record<string, any>;
  update: (patch: Record<string, unknown>) => void;
  channelId: number | null;
}) {
  const [templates, setTemplates] = useState<MetaTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasMediaHeader, setHasMediaHeader] = useState(false);

  useEffect(() => {
    if (!channelId) {
      setTemplates([]);
      return;
    }
    setLoading(true);
    templatesApi
      .list(channelId, 'APPROVED')
      .then((list) => setTemplates(list))
      .catch(() => toast.error('Falha ao carregar templates'))
      .finally(() => setLoading(false));
  }, [channelId]);

  useEffect(() => {
    if (!data.template_id) {
      setHasMediaHeader(false);
      return;
    }
    const tpl = templates.find((t) => t.id === data.template_id);
    if (!tpl) {
      setHasMediaHeader(false);
      return;
    }
    const header = (tpl.components || []).find(
      (c: any) => c.type === 'HEADER',
    ) as any;
    const mediaHeader =
      header && ['IMAGE', 'VIDEO', 'DOCUMENT'].includes(header.format);
    setHasMediaHeader(!!mediaHeader);
  }, [data.template_id, templates]);

  const selectedTemplate = templates.find((t) => t.id === data.template_id);
  const bodyComponent = (selectedTemplate?.components || []).find(
    (c: any) => c.type === 'BODY',
  ) as any;
  const bodyText: string = bodyComponent?.text || '';
  const paramMatches = [...bodyText.matchAll(/\{\{(\d+)\}\}/g)];
  const paramCount = paramMatches.length;

  const onSelectTemplate = (templateId: string) => {
    const tpl = templates.find((t) => t.id === Number(templateId));
    if (!tpl) {
      update({ template_id: null, template_name: null, template_params: [] });
      return;
    }
    const bodyC = (tpl.components || []).find((c: any) => c.type === 'BODY') as any;
    const text: string = bodyC?.text || '';
    const count = (text.match(/\{\{\d+\}\}/g) || []).length;
    const params: BroadcastTemplateParam[] = Array.from({ length: count }, () => ({
      type: 'fixed_text' as BroadcastTemplateParamType,
      value: '',
    }));
    update({
      template_id: tpl.id,
      template_name: tpl.name,
      template_params: params,
    });
  };

  const updateParam = (idx: number, patch: Partial<BroadcastTemplateParam>) => {
    const next: BroadcastTemplateParam[] = [...(data.template_params || [])];
    next[idx] = { ...next[idx], ...patch };
    update({ template_params: next });
  };

  if (!channelId) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        Selecione um canal padrão pro fluxo antes de configurar template.
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4">
      <div className="space-y-2">
        <Label>Template aprovado</Label>
        {loading ? (
          <div className="text-xs text-muted-foreground">Carregando templates…</div>
        ) : templates.length === 0 ? (
          <div className="text-xs text-muted-foreground">
            Nenhum template aprovado nesse canal. Sincronize em{' '}
            <a href="/canais" className="underline">
              Canais → Templates
            </a>
            .
          </div>
        ) : (
          <Select
            value={data.template_id ? String(data.template_id) : ''}
            onValueChange={onSelectTemplate}
          >
            <SelectTrigger>
              <SelectValue placeholder="Selecione um template" />
            </SelectTrigger>
            <SelectContent>
              {templates.map((t) => (
                <SelectItem key={t.id} value={String(t.id)}>
                  {t.name} ({t.language})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {hasMediaHeader && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-400">
          ⚠️ Este template tem cabeçalho com mídia. Ainda não suportamos isso —
          escolha um template só com texto ou aguarde a próxima versão.
        </div>
      )}

      {selectedTemplate && !hasMediaHeader && (
        <>
          <div className="space-y-1">
            <Label className="text-xs">Preview do corpo</Label>
            <div className="whitespace-pre-wrap rounded-md bg-muted/40 p-3 font-mono text-xs">
              {bodyText || '(template sem corpo)'}
            </div>
          </div>

          {paramCount > 0 && (
            <div className="space-y-3">
              <Label>Parâmetros</Label>
              {paramMatches.map((match, idx) => {
                const num = match[1];
                const p: BroadcastTemplateParam =
                  (data.template_params?.[idx] as BroadcastTemplateParam) || {
                    type: 'fixed_text',
                    value: '',
                  };
                return (
                  <div key={idx} className="space-y-1.5 rounded-md border p-2.5">
                    <div className="font-mono text-[11px] text-muted-foreground">{`{{${num}}}`}</div>
                    <Select
                      value={p.type}
                      onValueChange={(v) =>
                        updateParam(idx, {
                          type: v as BroadcastTemplateParamType,
                          value: '',
                        })
                      }
                    >
                      <SelectTrigger className="h-8 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="contact_name">Nome do contato</SelectItem>
                        <SelectItem value="contact_wa_id">Telefone do contato</SelectItem>
                        <SelectItem value="custom_var">Variável da lista CSV</SelectItem>
                        <SelectItem value="fixed_text">Texto fixo</SelectItem>
                      </SelectContent>
                    </Select>
                    {(p.type === 'custom_var' || p.type === 'fixed_text') && (
                      <Input
                        value={p.value || ''}
                        onChange={(e) => updateParam(idx, { value: e.target.value })}
                        placeholder={
                          p.type === 'custom_var'
                            ? 'nome da coluna do CSV (ex: curso)'
                            : 'texto fixo'
                        }
                        className="h-8 text-xs"
                      />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
