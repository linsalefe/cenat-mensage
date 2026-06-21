export interface User {
  id: number;
  email: string;
  name: string | null;
  is_admin: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export type ConnectionStatus = "open" | "close" | "connecting" | "unknown";

export interface Channel {
  id: number;
  name: string;
  phone_number: string | null;
  instance_name: string | null;
  type: string;
  provider: string;
  is_connected: boolean;
  is_active: boolean;
  operation_mode: "ai" | "chatbot" | "none";
  active_chatbot_flow_id: number | null;
  active_chatbot_flow_name?: string | null;
  connection_status?: ConnectionStatus;
  profile_name?: string | null;
  owner_jid?: string | null;
  created_at?: string | null;
  // Instagram (provider === "instagram")
  instagram_id?: string | null;
  page_id?: string | null;
}

export interface Contact {
  id: number;
  wa_id: string;
  name: string | null;
  lead_status: string | null;
  last_inbound_at: string | null;
  channel_id: number | null;
  channel_name?: string | null;
  is_group: boolean;
  updated_at: string | null;
}

export interface Message {
  id: number;
  wa_message_id: string;
  contact_wa_id: string;
  channel_id: number | null;
  direction: "inbound" | "outbound";
  message_type: string;
  content: string | null;
  timestamp: string;
  status: string;
  sent_by_ai: boolean;
  sender_name: string | null;
}

export interface ChatbotFlow {
  id: number;
  name: string;
  description: string | null;
  graph: { nodes: any[]; edges: any[] };
  published_graph: { nodes: any[]; edges: any[] } | null;
  is_published: boolean;
  version: number;
  default_channel_id: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ChatbotFlowListItem {
  id: number;
  name: string;
  description: string | null;
  is_published: boolean;
  version: number;
  default_channel_id: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export type BroadcastTemplateParamType =
  | "contact_name"
  | "contact_wa_id"
  | "custom_var"
  | "fixed_text";

export interface BroadcastTemplateParam {
  type: BroadcastTemplateParamType;
  value?: string;
}

// ============================================================
// Broadcast (Fase 5.2)
// ============================================================

export type FlowKind = "chatbot" | "broadcast";

export type AudienceType =
  | "all_groups"
  | "selected_groups"
  | "contacts_tag"
  | "csv"
  | "single_contact";

export type BroadcastStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface MessagePayload {
  text?: string | null;
  media_id?: number | null;
  media_url?: string | null;
  media_type?: string | null;
  media_mime?: string | null;
  caption?: string | null;
}

export interface BroadcastJob {
  id: number;
  name: string;
  flow_id: number | null;
  channel_id: number;
  audience_type: AudienceType;
  audience_spec: Record<string, any>;
  message_payload: MessagePayload;
  interval_seconds: number;
  scheduled_at: string | null;
  recurrence: Record<string, any> | null;
  status: BroadcastStatus;
  total_targets: number;
  sent_count: number;
  error_count: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  created_by: number | null;
  error_message: string | null;
}

export interface BroadcastLog {
  id: number;
  job_id: number;
  target_wa_id: string;
  target_name: string | null;
  status: "sent" | "error" | "skipped";
  error_detail: string | null;
  sent_at: string | null;
}

export interface MediaAsset {
  id: number;
  url: string;
  filename: string;
  media_type: "image" | "audio" | "video" | "document";
  mime_type: string;
  size_bytes: number;
  uploaded_by: number | null;
  created_at: string | null;
}

export interface EvolutionGroup {
  id: string;
  subject: string;
  picture_url: string | null;
  size: number | null;
  owner: string | null;
  desc: string | null;
  created_at: number | string | null;
}

export interface MetaChannelHealth {
  channel_id: number;
  ok: boolean;
  verified_name?: string | null;
  display_phone_number?: string | null;
  quality_rating?: "GREEN" | "YELLOW" | "RED" | "UNKNOWN" | null;
  code_verification_status?: string | null;
  name_status?: string | null;
  platform_type?: string | null;
  status_code?: number;
  error?: unknown;
}

export interface MetaChannelCreate {
  name: string;
  phone_number: string;
  phone_number_id: string;
  waba_id: string;
  whatsapp_token: string;
  operation_mode?: "ai" | "chatbot" | "none";
}

export interface MetaChannelUpdate {
  name?: string;
  whatsapp_token?: string;
  is_active?: boolean;
  operation_mode?: "ai" | "chatbot" | "none";
}

export interface MetaSendTextRequest {
  to: string;
  text: string;
}

export interface MetaSendTemplateRequest {
  to: string;
  template_name: string;
  language_code?: string;
  components?: unknown[];
}

export interface MetaSendResponse {
  status: string;
  wa_message_id: string;
  graph_response?: unknown;
}

export interface MetaTemplate {
  id: number;
  channel_id: number;
  name: string;
  language: string;
  category: string | null;
  status: string;
  components: Array<Record<string, unknown>> | null;
  meta_template_id: string | null;
  last_synced_at: string | null;
}

export interface ContactList {
  id: number;
  name: string;
  description: string | null;
  channel_id: number | null;
  created_by: number | null;
  created_at: string | null;
  updated_at: string | null;
  member_count: number;
}

// ============================================================
// Instagram — canal + automações (Sprints 1, 2 e 3)
// ============================================================
export interface InstagramChannelCreate {
  name?: string;
  instagram_id: string;
  page_id?: string;
  access_token: string;
  username?: string;
}

export interface InstagramChannelUpdate {
  name?: string;
  access_token?: string;
  is_active?: boolean;
}

export interface InstagramChannelHealth {
  channel_id: number;
  ok: boolean;
  username?: string | null;
  name?: string | null;
  profile_picture_url?: string | null;
  status_code?: number;
  error?: unknown;
}

export interface InstagramSendResponse {
  status: string;
  message_id: string;
  graph_response?: unknown;
}

export type IgTriggerType =
  | "dm_received"
  | "comment"
  | "reaction"
  | "postback"
  | "mention"
  | "story_reply";

export type IgActionType = "send_dm" | "private_reply" | "public_comment_reply";

export type IgMatchMode = "any" | "all" | "exact";

export interface IgTriggerConfig {
  keywords?: string[];
  match?: IgMatchMode;
  media_id?: string | null;
  emoji?: string;
  payload?: string;
}

export interface IgActionConfig {
  text?: string;
}

export interface InstagramAutomation {
  id: number;
  channel_id: number;
  name: string;
  trigger_type: IgTriggerType;
  trigger_config: IgTriggerConfig;
  action_type: IgActionType;
  action_config: IgActionConfig;
  once_per_contact: boolean;
  is_active: boolean;
  priority: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface InstagramAutomationCreate {
  name: string;
  trigger_type: IgTriggerType;
  trigger_config: IgTriggerConfig;
  action_type: IgActionType;
  action_config: IgActionConfig;
  once_per_contact?: boolean;
  is_active?: boolean;
  priority?: number;
}

export type InstagramAutomationUpdate = Partial<InstagramAutomationCreate>;

// ============================================================
// CRM Pipeline (kanban)
// ============================================================
export interface PipelineColumn {
  key: string;
  label: string;
  color: string;
  order: number;
}

export interface Pipeline {
  id: number;
  name: string;
  columns: PipelineColumn[];
  is_default: boolean;
  order: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface KanbanCard {
  id: number;
  wa_id: string;
  name: string | null;
  lead_status: string | null;
  pipeline_id: number | null;
  channel_id: number | null;
  provider: string | null;
  deal_value: number | null;
  notes: string | null;
  is_group: boolean;
  last_inbound_at: string | null;
  updated_at: string | null;
}

export interface InstagramAutomationExecution {
  id: number;
  automation_id: number;
  channel_id: number | null;
  trigger_ref: string;
  contact_wa_id: string | null;
  status: "sent" | "error" | "skipped";
  detail: string | null;
  created_at: string | null;
}

export interface ContactListMember {
  id: number;
  list_id: number;
  wa_id: string;
  name: string | null;
  custom_vars: Record<string, string>;
  opted_out: boolean;
  added_at: string | null;
}

export interface CsvImportResult {
  list_id: number;
  imported: number;
  skipped_duplicates: number;
  errors: Array<{ line: number; reason: string }>;
  detected_columns: string[];
  total_lines: number;
}
