'use client';

import { Trash2, Plus, X } from 'lucide-react';
import { type Node } from '@xyflow/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { NODE_META, type NodeKind } from './node-catalog';

export interface KanbanCol { key: string; label: string; }
export interface UserOpt { id: number; name: string; }
export interface PipelineOpt {
  id: number;
  name: string;
  is_default: boolean;
  columns: KanbanCol[];
}

interface InspectorProps {
  node: Node;
  onChange: (newData: Record<string, any>) => void;
  onDelete: () => void;
  kanbanColumns: KanbanCol[];  // fallback/compat
  users: UserOpt[];
  pipelines: PipelineOpt[];
}

export function NodeInspector({ node, onChange, onDelete, kanbanColumns, users, pipelines }: InspectorProps) {
  const kind = (node.type || 'message') as NodeKind;
  const meta = NODE_META[kind];
  const data = (node.data || {}) as Record<string, any>;
  const Icon = meta.icon;

  const update = (patch: Record<string, any>) => onChange({ ...data, ...patch });

  return (
    <div className="w-[340px] flex-shrink-0 border-l border-border bg-card flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-3 p-4 border-b border-border">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${meta.colorClass}`}>
          <Icon className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Editando</div>
          <div className="text-sm font-semibold truncate">{meta.label}</div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {kind === 'trigger' && <TriggerForm data={data} update={update} />}
        {kind === 'message' && <MessageForm data={data} update={update} />}
        {kind === 'buttons' && <ButtonsForm data={data} update={update} />}
        {kind === 'input' && <InputForm data={data} update={update} />}
        {kind === 'condition' && <ConditionForm data={data} update={update} />}
        {kind === 'tag' && <TagForm data={data} update={update} />}
        {kind === 'move_stage' && <StageForm data={data} update={update} kanbanColumns={kanbanColumns} pipelines={pipelines} />}
        {kind === 'handoff' && <HandoffForm data={data} update={update} kanbanColumns={kanbanColumns} users={users} pipelines={pipelines} />}
        {kind === 'delay' && <DelayForm data={data} update={update} />}
        {kind === 'http_request' && <HttpRequestForm data={data} update={update} />}
        {kind === 'webhook_out' && <WebhookOutForm data={data} update={update} />}
        {kind === 'end' && <p className="text-sm text-muted-foreground">Este nó encerra o fluxo. Sem configurações.</p>}
        <VarHint kind={kind} />
      </div>

      <div className="p-4 border-t border-border">
        <Button
          variant="outline" size="sm"
          className="w-full text-destructive hover:text-destructive hover:bg-destructive/10"
          onClick={onDelete}
        >
          <Trash2 className="w-4 h-4 mr-2" /> Excluir este nó
        </Button>
      </div>
    </div>
  );
}

function VarHint({ kind }: { kind: NodeKind }) {
  if (!['message', 'buttons', 'input', 'handoff'].includes(kind)) return null;
  return (
    <div className="rounded-lg bg-muted/50 border border-border p-3 text-[11px] text-muted-foreground leading-relaxed">
      <p className="font-medium text-foreground mb-1">Variáveis disponíveis</p>
      <p>
        Use <code className="bg-background px-1 py-0.5 rounded">{'{nome}'}</code> e{' '}
        <code className="bg-background px-1 py-0.5 rounded">{'{telefone}'}</code> do contato,
        além das que você capturar com nós <strong>Captura</strong>.
      </p>
    </div>
  );
}

function TriggerForm({ data, update }: { data: any; update: (p: any) => void }) {
  return (
    <>
      <div className="space-y-2">
        <Label>Quando acionar</Label>
        <Select value={data.mode || 'any_message'} onValueChange={(v) => update({ mode: v })}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="any_message">Qualquer primeira mensagem</SelectItem>
            <SelectItem value="keyword">Palavra-chave</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {data.mode === 'keyword' && (
        <div className="space-y-2">
          <Label htmlFor="kw">Palavra-chave</Label>
          <Input id="kw" value={data.keyword || ''} onChange={(e) => update({ keyword: e.target.value })} placeholder="ex: menu, oi, boleto" />
          <p className="text-[11px] text-muted-foreground">Aceita quando a palavra aparece em qualquer lugar da mensagem.</p>
        </div>
      )}
    </>
  );
}

function MessageForm({ data, update }: { data: any; update: (p: any) => void }) {
  return (
    <div className="space-y-2">
      <Label htmlFor="msg-text">Mensagem</Label>
      <Textarea id="msg-text" value={data.text || ''} onChange={(e) => update({ text: e.target.value })} placeholder="Olá {nome}! Como posso ajudar?" rows={6} className="resize-none" />
    </div>
  );
}

function ButtonsForm({ data, update }: { data: any; update: (p: any) => void }) {
  const buttons: Array<{ id: string; label: string }> = data.buttons || [];
  const updateBtn = (idx: number, label: string) => {
    const next = [...buttons]; next[idx] = { ...next[idx], label }; update({ buttons: next });
  };
  const addBtn = () => {
    if (buttons.length >= 10) return;
    update({ buttons: [...buttons, { id: `b_${Math.random().toString(36).slice(2, 8)}`, label: `Opção ${buttons.length + 1}` }] });
  };
  const removeBtn = (idx: number) => update({ buttons: buttons.filter((_, i) => i !== idx) });

  return (
    <>
      <div className="space-y-2">
        <Label htmlFor="bt-text">Pergunta / Texto</Label>
        <Textarea id="bt-text" value={data.text || ''} onChange={(e) => update({ text: e.target.value })} placeholder="Escolha uma opção:" rows={3} className="resize-none" />
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>Botões ({buttons.length})</Label>
          {buttons.length < 10 && (
            <Button size="sm" variant="ghost" onClick={addBtn} className="h-7 px-2 text-xs"><Plus className="w-3 h-3 mr-1" /> Adicionar</Button>
          )}
        </div>
        <div className="space-y-1.5">
          {buttons.map((btn, idx) => (
            <div key={btn.id} className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground font-mono w-5 text-center">{idx + 1}</span>
              <Input value={btn.label} onChange={(e) => updateBtn(idx, e.target.value)} placeholder="Texto do botão" className="h-8 text-sm" />
              <Button size="icon" variant="ghost" onClick={() => removeBtn(idx)} className="h-8 w-8 flex-shrink-0 text-muted-foreground hover:text-destructive" disabled={buttons.length <= 1}>
                <X className="w-3.5 h-3.5" />
              </Button>
            </div>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground">Ligue cada botão ao nó seguinte arrastando da bolinha à direita.</p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="cap">Guardar escolha em (opcional)</Label>
        <Input id="cap" value={data.capture_to || ''} onChange={(e) => update({ capture_to: e.target.value })} placeholder="ex: opcao_escolhida" />
      </div>
    </>
  );
}

function InputForm({ data, update }: { data: any; update: (p: any) => void }) {
  return (
    <>
      <div className="space-y-2">
        <Label htmlFor="ip-prompt">Pergunta</Label>
        <Textarea id="ip-prompt" value={data.prompt || ''} onChange={(e) => update({ prompt: e.target.value })} placeholder="Qual seu CPF?" rows={3} className="resize-none" />
      </div>
      <div className="space-y-2">
        <Label htmlFor="ip-var">Guardar em (variável)</Label>
        <Input id="ip-var" value={data.variable || ''} onChange={(e) => update({ variable: e.target.value })} placeholder="ex: cpf, email" />
        <p className="text-[11px] text-muted-foreground">
          Use depois como <code className="bg-muted px-1 py-0.5 rounded">{`{${data.variable || 'variavel'}}`}</code>.
        </p>
      </div>
      <div className="space-y-2">
        <Label>Tipo de validação</Label>
        <Select value={data.validation || 'text'} onValueChange={(v) => update({ validation: v })}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="text">Texto livre</SelectItem>
            <SelectItem value="email">E-mail</SelectItem>
            <SelectItem value="cpf">CPF</SelectItem>
            <SelectItem value="phone">Telefone</SelectItem>
            <SelectItem value="number">Número</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="ip-err">Mensagem de erro (se inválido)</Label>
        <Input id="ip-err" value={data.error_message || ''} onChange={(e) => update({ error_message: e.target.value })} placeholder="Formato inválido." />
      </div>
    </>
  );
}

function ConditionForm({ data, update }: { data: any; update: (p: any) => void }) {
  return (
    <>
      <div className="space-y-2">
        <Label htmlFor="cd-var">Variável</Label>
        <Input id="cd-var" value={data.variable || ''} onChange={(e) => update({ variable: e.target.value })} placeholder="ex: opcao_escolhida" />
      </div>
      <div className="space-y-2">
        <Label>Operador</Label>
        <Select value={data.operator || 'equals'} onValueChange={(v) => update({ operator: v })}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="equals">igual a</SelectItem>
            <SelectItem value="not_equals">diferente de</SelectItem>
            <SelectItem value="contains">contém</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="cd-val">Valor</Label>
        <Input id="cd-val" value={data.value || ''} onChange={(e) => update({ value: e.target.value })} placeholder="ex: Boleto" />
      </div>
      <p className="text-[11px] text-muted-foreground">
        Saídas: <span className="text-emerald-600 dark:text-emerald-400 font-medium">verdadeiro</span> e <span className="text-rose-600 dark:text-rose-400 font-medium">falso</span>.
      </p>
    </>
  );
}

function TagForm({ data, update }: { data: any; update: (p: any) => void }) {
  return (
    <div className="space-y-2">
      <Label htmlFor="tg">Nome da tag</Label>
      <Input id="tg" value={data.tag_name || ''} onChange={(e) => update({ tag_name: e.target.value })} placeholder="ex: Pediu Boleto" />
      <p className="text-[11px] text-muted-foreground">Se não existir, é criada automaticamente.</p>
    </div>
  );
}

// ============================================================
// MOVE STAGE — cascata Pipeline → Estágio
// ============================================================
function StageForm({
  data, update, kanbanColumns, pipelines,
}: { data: any; update: (p: any) => void; kanbanColumns: KanbanCol[]; pipelines: PipelineOpt[] }) {
  return <PipelineStageCascade data={data} update={update} pipelines={pipelines} fallbackColumns={kanbanColumns} />;
}

function HandoffForm({
  data, update, kanbanColumns, users, pipelines,
}: { data: any; update: (p: any) => void; kanbanColumns: KanbanCol[]; users: UserOpt[]; pipelines: PipelineOpt[] }) {
  return (
    <>
      <div className="space-y-2">
        <Label htmlFor="ho-title">Título da tarefa</Label>
        <Input id="ho-title" value={data.task_title || ''} onChange={(e) => update({ task_title: e.target.value })} placeholder="Atender {nome}" />
      </div>
      <div className="space-y-2">
        <Label htmlFor="ho-desc">Descrição (opcional)</Label>
        <Textarea id="ho-desc" value={data.task_description || ''} onChange={(e) => update({ task_description: e.target.value })} placeholder="Contexto..." rows={3} className="resize-none" />
        <p className="text-[11px] text-muted-foreground">Variáveis capturadas são anexadas automaticamente.</p>
      </div>
      <div className="space-y-2">
        <Label>Atribuir para</Label>
        <Select value={data.assigned_to_user_id ? String(data.assigned_to_user_id) : ''} onValueChange={(v) => update({ assigned_to_user_id: Number(v) })}>
          <SelectTrigger><SelectValue placeholder="Selecione..." /></SelectTrigger>
          <SelectContent>{users.map((u) => <SelectItem key={u.id} value={String(u.id)}>{u.name}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <Label>Prioridade</Label>
        <Select value={data.priority || 'media'} onValueChange={(v) => update({ priority: v })}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="alta">Alta</SelectItem>
            <SelectItem value="media">Média</SelectItem>
            <SelectItem value="baixa">Baixa</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <Label>Mover o contato para (opcional)</Label>
        <PipelineStageCascade
          data={data}
          update={update}
          pipelines={pipelines}
          fallbackColumns={kanbanColumns}
          allowNone
        />
      </div>
    </>
  );
}


// ============================================================
// DELAY
// ============================================================
function DelayForm({ data, update }: { data: any; update: (p: any) => void }) {
  const amount = data.amount ?? 1;
  const unit = data.unit ?? 'minutes';

  const unitLabel: Record<string, string> = {
    minutes: amount === 1 ? 'minuto' : 'minutos',
    hours: amount === 1 ? 'hora' : 'horas',
    days: amount === 1 ? 'dia' : 'dias',
  };

  return (
    <>
      <div className="space-y-2">
        <Label>Aguardar</Label>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            min={1}
            max={999}
            value={amount}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              update({ amount: isNaN(v) || v < 1 ? 1 : v });
            }}
            className="w-24"
          />
          <Select value={unit} onValueChange={(v) => update({ unit: v })}>
            <SelectTrigger className="flex-1"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="minutes">Minutos</SelectItem>
              <SelectItem value="hours">Horas</SelectItem>
              <SelectItem value="days">Dias</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="rounded-lg bg-muted/50 border border-border p-3 text-[11px] text-muted-foreground leading-relaxed">
        <p className="font-medium text-foreground mb-1">Como funciona</p>
        <p>
          O fluxo pausa aqui e retoma automaticamente depois de <strong>{amount} {unitLabel[unit]}</strong>.
          Durante a espera, novas mensagens do contato não avançam o fluxo.
        </p>
      </div>
    </>
  );
}


// ============================================================
// HTTP REQUEST
// ============================================================
function HttpRequestForm({ data, update }: { data: any; update: (p: any) => void }) {
  const method = (data.method || 'GET').toUpperCase();
  const headers: Array<{ key: string; value: string }> = data.headers || [];
  const bodyMode = data.body_mode || 'none';
  const prefix = data.response_var_prefix || 'http';

  const addHeader = () => update({ headers: [...headers, { key: '', value: '' }] });
  const updateHeader = (i: number, field: 'key' | 'value', v: string) => {
    const next = [...headers];
    next[i] = { ...next[i], [field]: v };
    update({ headers: next });
  };
  const removeHeader = (i: number) => update({ headers: headers.filter((_: any, idx: number) => idx !== i) });

  return (
    <>
      <div className="space-y-2">
        <Label>Método</Label>
        <Select value={method} onValueChange={(v) => update({ method: v })}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="GET">GET</SelectItem>
            <SelectItem value="POST">POST</SelectItem>
            <SelectItem value="PUT">PUT</SelectItem>
            <SelectItem value="PATCH">PATCH</SelectItem>
            <SelectItem value="DELETE">DELETE</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="http-url">URL</Label>
        <Input
          id="http-url"
          value={data.url || ''}
          onChange={(e) => update({ url: e.target.value })}
          placeholder="https://api.exemplo.com/clientes/{cpf}"
          className="font-mono text-xs"
        />
        <p className="text-[11px] text-muted-foreground">
          Use <code className="bg-muted px-1 py-0.5 rounded">{'{variavel}'}</code> pra interpolar valores capturados.
        </p>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>Headers</Label>
          <Button size="sm" variant="ghost" onClick={addHeader} className="h-7 px-2 text-xs">
            <Plus className="w-3 h-3 mr-1" /> Adicionar
          </Button>
        </div>
        {headers.length === 0 && (
          <p className="text-[11px] text-muted-foreground italic">Nenhum header configurado</p>
        )}
        <div className="space-y-1.5">
          {headers.map((h: any, i: number) => (
            <div key={i} className="flex items-center gap-1.5">
              <Input
                value={h.key}
                onChange={(e) => updateHeader(i, 'key', e.target.value)}
                placeholder="Authorization"
                className="h-8 text-xs font-mono flex-1"
              />
              <Input
                value={h.value}
                onChange={(e) => updateHeader(i, 'value', e.target.value)}
                placeholder="Bearer abc..."
                className="h-8 text-xs font-mono flex-1"
              />
              <Button
                size="icon"
                variant="ghost"
                onClick={() => removeHeader(i)}
                className="h-8 w-8 flex-shrink-0 text-muted-foreground hover:text-destructive"
              >
                <X className="w-3.5 h-3.5" />
              </Button>
            </div>
          ))}
        </div>
      </div>

      {method !== 'GET' && method !== 'DELETE' && (
        <>
          <div className="space-y-2">
            <Label>Corpo da requisição</Label>
            <Select value={bodyMode} onValueChange={(v) => update({ body_mode: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Sem corpo</SelectItem>
                <SelectItem value="json">JSON</SelectItem>
                <SelectItem value="text">Texto / form</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {bodyMode !== 'none' && (
            <div className="space-y-2">
              <Label htmlFor="http-body">
                {bodyMode === 'json' ? 'Corpo JSON' : 'Corpo'}
              </Label>
              <Textarea
                id="http-body"
                value={data.body || ''}
                onChange={(e) => update({ body: e.target.value })}
                placeholder={bodyMode === 'json' ? '{"nome":"{nome}","cpf":"{cpf}"}' : 'chave=valor&outra=teste'}
                rows={5}
                className="font-mono text-xs resize-none"
              />
              <p className="text-[11px] text-muted-foreground">
                Variáveis funcionam também aqui. JSON deve ser válido depois da interpolação.
              </p>
            </div>
          )}
        </>
      )}

      <div className="space-y-2">
        <Label htmlFor="http-prefix">Prefixo das variáveis de resposta</Label>
        <Input
          id="http-prefix"
          value={prefix}
          onChange={(e) => update({ response_var_prefix: e.target.value.replace(/[^a-zA-Z_]/g, '') })}
          placeholder="http"
          className="font-mono text-xs"
        />
        <div className="text-[11px] text-muted-foreground leading-relaxed space-y-0.5">
          <p>Após a execução você pode usar:</p>
          <ul className="pl-3 space-y-0.5">
            <li>• <code className="bg-muted px-1 rounded">{`{${prefix}_status}`}</code> — código HTTP</li>
            <li>• <code className="bg-muted px-1 rounded">{`{${prefix}_ok}`}</code> — &quot;true&quot; se 2xx</li>
            <li>• <code className="bg-muted px-1 rounded">{`{${prefix}_response_raw}`}</code> — body cru</li>
            <li>• <code className="bg-muted px-1 rounded">{`{${prefix}_response.campo}`}</code> — acessa JSON</li>
          </ul>
        </div>
      </div>

      <div className="rounded-lg bg-muted/50 border border-border p-3 text-[11px] text-muted-foreground leading-relaxed">
        <p className="font-medium text-foreground mb-1">Dois caminhos de saída</p>
        <p>
          <span className="text-emerald-600 dark:text-emerald-400 font-medium">Sucesso</span>:
          resposta 2xx sem erro de conexão.
          <br />
          <span className="text-rose-600 dark:text-rose-400 font-medium">Erro</span>:
          4xx, 5xx, timeout ou falha de rede.
        </p>
      </div>
    </>
  );
}


// ============================================================
// WEBHOOK OUT
// ============================================================
function WebhookOutForm({ data, update }: { data: any; update: (p: any) => void }) {
  const mode = data.payload_mode || 'auto';
  const headers: Array<{ key: string; value: string }> = data.headers || [];

  const addHeader = () => update({ headers: [...headers, { key: '', value: '' }] });
  const updateHeader = (i: number, field: 'key' | 'value', v: string) => {
    const next = [...headers];
    next[i] = { ...next[i], [field]: v };
    update({ headers: next });
  };
  const removeHeader = (i: number) => update({ headers: headers.filter((_: any, idx: number) => idx !== i) });

  const autoPreview = JSON.stringify({
    event: data.event_name || 'chatbot_event',
    session_id: 123,
    contact: { name: '{nome}', wa_id: '{telefone}' },
    variables: { '...': 'variáveis capturadas no fluxo' },
    timestamp: '2026-04-21T15:30:00Z',
  }, null, 2);

  return (
    <>
      <div className="space-y-2">
        <Label htmlFor="wh-url">URL do endpoint</Label>
        <Input
          id="wh-url"
          value={data.url || ''}
          onChange={(e) => update({ url: e.target.value })}
          placeholder="https://seu-servidor.com/webhook"
          className="font-mono text-xs"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="wh-event">Nome do evento</Label>
        <Input
          id="wh-event"
          value={data.event_name || ''}
          onChange={(e) => update({ event_name: e.target.value.replace(/\s+/g, '_') })}
          placeholder="lead_pediu_boleto"
          className="font-mono text-xs"
        />
        <p className="text-[11px] text-muted-foreground">
          Identifica esse evento no lado do cliente. Use snake_case.
        </p>
      </div>

      <div className="space-y-2">
        <Label>Payload</Label>
        <Select value={mode} onValueChange={(v) => update({ payload_mode: v })}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">Automático (recomendado)</SelectItem>
            <SelectItem value="custom">Customizado</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {mode === 'auto' ? (
        <div className="space-y-2">
          <Label className="text-[11px] text-muted-foreground">Preview do JSON que será enviado</Label>
          <pre className="text-[10px] bg-muted/50 border border-border rounded-md p-2 overflow-x-auto font-mono max-h-[200px] overflow-y-auto">
{autoPreview}
          </pre>
        </div>
      ) : (
        <div className="space-y-2">
          <Label htmlFor="wh-custom">JSON customizado</Label>
          <Textarea
            id="wh-custom"
            value={data.custom_payload || ''}
            onChange={(e) => update({ custom_payload: e.target.value })}
            placeholder={'{"cliente":"{nome}","telefone":"{telefone}","cpf":"{cpf}"}'}
            rows={6}
            className="font-mono text-xs resize-none"
          />
          <p className="text-[11px] text-muted-foreground">
            Variáveis funcionam aqui. JSON deve ser válido depois da interpolação.
          </p>
        </div>
      )}

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>Headers adicionais</Label>
          <Button size="sm" variant="ghost" onClick={addHeader} className="h-7 px-2 text-xs">
            <Plus className="w-3 h-3 mr-1" /> Adicionar
          </Button>
        </div>
        {headers.length === 0 && (
          <p className="text-[11px] text-muted-foreground italic">
            Nenhum header — Content-Type: application/json já vai por padrão
          </p>
        )}
        <div className="space-y-1.5">
          {headers.map((h: any, i: number) => (
            <div key={i} className="flex items-center gap-1.5">
              <Input
                value={h.key}
                onChange={(e) => updateHeader(i, 'key', e.target.value)}
                placeholder="X-API-Key"
                className="h-8 text-xs font-mono flex-1"
              />
              <Input
                value={h.value}
                onChange={(e) => updateHeader(i, 'value', e.target.value)}
                placeholder="abc123..."
                className="h-8 text-xs font-mono flex-1"
              />
              <Button
                size="icon"
                variant="ghost"
                onClick={() => removeHeader(i)}
                className="h-8 w-8 flex-shrink-0 text-muted-foreground hover:text-destructive"
              >
                <X className="w-3.5 h-3.5" />
              </Button>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-lg bg-muted/50 border border-border p-3 text-[11px] text-muted-foreground leading-relaxed">
        <p className="font-medium text-foreground mb-1">Fire-and-forget</p>
        <p>
          O fluxo continua imediatamente, sem esperar resposta. Se o endpoint falhar,
          o erro é registrado no log do servidor e o fluxo <strong>não é interrompido</strong>.
          Para tratar erro no fluxo, use <strong>HTTP Request</strong>.
        </p>
      </div>
    </>
  );
}


// ============================================================
// Componente reusável: Pipeline + Stage em cascata
// ============================================================
function PipelineStageCascade({
  data, update, pipelines, fallbackColumns, allowNone = false,
}: {
  data: any;
  update: (p: any) => void;
  pipelines: PipelineOpt[];
  fallbackColumns: KanbanCol[];
  allowNone?: boolean;
}) {
  // Determina pipeline selecionado (ou default)
  const selectedPipelineId: number | null = data.pipeline_id
    ? Number(data.pipeline_id)
    : null;

  const selectedPipeline = pipelines.find((p) => p.id === selectedPipelineId) || null;

  // Colunas disponíveis: do pipeline escolhido, OU do default se nenhum escolhido, OU fallback
  const columns: KanbanCol[] =
    selectedPipeline?.columns?.length
      ? selectedPipeline.columns
      : pipelines.find((p) => p.is_default)?.columns || fallbackColumns;

  const hasPipelines = pipelines.length > 0;
  const multiplePipelines = pipelines.length > 1;

  const handlePipelineChange = (v: string) => {
    if (v === '__default__') {
      // Voltar pro default = remove pipeline_id e limpa stage
      const next = { ...data };
      delete next.pipeline_id;
      next.stage = allowNone ? '' : next.stage;
      update(next);
      return;
    }
    const pid = Number(v);
    update({ ...data, pipeline_id: pid, stage: '' }); // limpa stage ao trocar pipeline
  };

  const handleStageChange = (v: string) => {
    if (v === '__none__') {
      update({ ...data, stage: '' });
      return;
    }
    update({ ...data, stage: v });
  };

  return (
    <div className="space-y-2">
      {multiplePipelines && (
        <div className="space-y-1.5">
          <Label className="text-[11px] text-muted-foreground">Pipeline</Label>
          <Select
            value={selectedPipelineId ? String(selectedPipelineId) : '__default__'}
            onValueChange={handlePipelineChange}
          >
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__default__">Pipeline do contato (atual)</SelectItem>
              {pipelines.map((p) => (
                <SelectItem key={p.id} value={String(p.id)}>
                  {p.name}{p.is_default ? ' (padrão)' : ''}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      <div className="space-y-1.5">
        <Label className="text-[11px] text-muted-foreground">
          {multiplePipelines ? 'Estágio' : 'Mover para'}
        </Label>
        {columns.length > 0 ? (
          <Select
            value={data.stage || (allowNone ? '__none__' : '')}
            onValueChange={handleStageChange}
          >
            <SelectTrigger>
              <SelectValue placeholder={allowNone ? 'Não mover' : 'Selecione...'} />
            </SelectTrigger>
            <SelectContent>
              {allowNone && <SelectItem value="__none__">Não mover</SelectItem>}
              {columns.map((c) => (
                <SelectItem key={c.key} value={c.key}>{c.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <Input
            value={data.stage || ''}
            onChange={(e) => update({ ...data, stage: e.target.value })}
            placeholder={hasPipelines ? 'Selecione um pipeline primeiro' : 'ex: em_contato'}
            disabled={multiplePipelines && !selectedPipeline}
          />
        )}
      </div>
    </div>
  );
}
