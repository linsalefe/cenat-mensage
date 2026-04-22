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
