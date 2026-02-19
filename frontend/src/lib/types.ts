export interface User {
  id: string;
  email: string;
  full_name: string;
  organization: string | null;
  is_active: boolean;
  created_at: string;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  agent_type: string;
  status: "active" | "suspended" | "revoked" | "panic";
  trust_score: number;
  identity_fingerprint: string;
  created_at: string;
  wallet_balance?: number;
  daily_limit?: number;
  spent_today?: number;
  active_permissions?: number;
  total_actions_24h?: number;
  autonomy_level?: string;
}

export interface Wallet {
  id: string;
  agent_id: string;
  balance_usd: number;
  daily_limit_usd: number;
  monthly_limit_usd: number;
  spent_today_usd: number;
  spent_this_month_usd: number;
  is_frozen: boolean;
}

export interface Permission {
  id: string;
  service_name: string;
  allowed_actions: string[];
  max_requests_per_hour: number;
  time_window_start: string;
  time_window_end: string;
  max_records_per_request: number;
  requires_hitl: boolean;
  is_active: boolean;
}

export interface AuditEntry {
  id: number;
  agent_id: string;
  action_type: string;
  service_name: string | null;
  permission_granted: boolean;
  cost_usd: number;
  response_code: number | null;
  duration_ms: number | null;
  timestamp: string;
}

export interface HITLItem {
  id: string;
  agent_id: string;
  action_description: string;
  estimated_cost_usd: number;
  status: string;
  created_at: string;
  expires_at: string;
}

export interface DashboardStats {
  total_agents: number;
  active_agents: number;
  suspended_agents: number;
  total_requests_24h: number;
  total_blocked_24h: number;
  total_spend_24h: number;
  total_spend_month: number;
  avg_trust_score: number;
  pending_hitl: number;
  circuit_breaker_triggers_24h: number;
  hourly_spend: { hour: string; spend: number; blocked: number }[];
  top_services: { service: string; requests: number; cost: number }[];
}

export interface WSMessage {
  event: string;
  data: Record<string, any>;
}

export interface LoginResponse {
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  mfa_required?: boolean;
  mfa_token?: string;
}

export interface ProxyRequest {
  agent_id: string;
  service_name: string;
  action: string;
  target_url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: unknown;
  prompt?: string;
  model?: string;
  estimated_cost_usd?: number;
}

export interface ProxyResponse {
  request_id: string;
  status: "executed" | "blocked" | "hitl_pending";
  response_code?: number;
  response_body?: unknown;
  cost_charged_usd: number;
  policy_result?: Record<string, unknown>;
  message: string;
  duration_ms?: number;
}