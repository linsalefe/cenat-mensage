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
  created_at: string | null;
  updated_at: string | null;
}

export interface ChatbotFlowListItem {
  id: number;
  name: string;
  description: string | null;
  is_published: boolean;
  version: number;
  created_at: string | null;
  updated_at: string | null;
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
