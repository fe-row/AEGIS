import type { DashboardStats, Agent, Wallet, Permission, AuditEntry, HITLItem, User } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API = `${API_BASE}/api/v1`;

// ── Token management ──

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("aegis_token");
}

function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("aegis_refresh_token");
}

function saveTokens(access: string, refresh: string) {
  localStorage.setItem("aegis_token", access);
  localStorage.setItem("aegis_refresh_token", refresh);
}

export async function logout() {
  // Invalidate token server-side (fire-and-forget)
  const token = localStorage.getItem("aegis_token");
  if (token) {
    fetch(`${API}/auth/logout`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
      },
    }).catch(() => {});
  }
  localStorage.removeItem("aegis_token");
  localStorage.removeItem("aegis_refresh_token");
  window.location.href = "/";
}

// ── Request wrapper with auto-refresh ──

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const doRequest = async (token: string | null) => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string> || {}),
    };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return fetch(`${API}${path}`, { ...options, headers });
  };

  let res = await doRequest(getToken());

  // Auto-refresh on 401
  if (res.status === 401) {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      try {
        const refreshRes = await fetch(`${API}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });

        if (refreshRes.ok) {
          const data = await refreshRes.json();
          saveTokens(data.access_token, data.refresh_token);
          res = await doRequest(data.access_token);
        } else {
          logout();
          throw new Error("Session expired");
        }
      } catch {
        logout();
        throw new Error("Session expired");
      }
    } else {
      logout();
      throw new Error("Not authenticated");
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Auth ──

export async function login(email: string, password: string) {
  const data = await request<{ access_token: string; refresh_token: string; expires_in: number }>(
    "/auth/login",
    { method: "POST", body: JSON.stringify({ email, password }) }
  );
  saveTokens(data.access_token, data.refresh_token);
  return data;
}

export async function register(
  email: string, password: string, full_name: string, organization?: string
) {
  return request<User>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, full_name, organization }),
  });
}

export async function getMe() {
  return request<User>("/auth/me");
}

// ── Agents ──

export async function getAgents() {
  return request<Agent[]>("/agents/");
}

export async function getAgent(id: string) {
  return request<Agent>(`/agents/${id}`);
}

export async function createAgent(data: { name: string; description: string; agent_type: string }) {
  return request<Agent>("/agents/", { method: "POST", body: JSON.stringify(data) });
}

export async function suspendAgent(id: string) {
  return request(`/agents/${id}/suspend`, { method: "POST" });
}

export async function activateAgent(id: string) {
  return request(`/agents/${id}/activate`, { method: "POST" });
}

// ── Permissions ──

export async function getPermissions(agentId: string) {
  return request<Permission[]>(`/agents/${agentId}/permissions`);
}

export async function addPermission(agentId: string, data: any) {
  return request<Permission>(`/agents/${agentId}/permissions`, {
    method: "POST", body: JSON.stringify(data),
  });
}

export async function deletePermission(agentId: string, permId: string) {
  return request(`/agents/${agentId}/permissions/${permId}`, { method: "DELETE" });
}

// ── Secrets ──

export async function storeSecret(
  agentId: string, data: { service_name: string; secret_value: string }
) {
  return request(`/agents/${agentId}/secrets`, {
    method: "POST", body: JSON.stringify(data),
  });
}

// ── Wallets ──

export async function getWallet(agentId: string) {
  return request<Wallet>(`/wallets/${agentId}`);
}

export async function topUpWallet(agentId: string, amount: number) {
  return request<Wallet>(`/wallets/${agentId}/top-up`, {
    method: "POST", body: JSON.stringify({ amount_usd: amount }),
  });
}

export async function configureWallet(
  agentId: string, data: { daily_limit_usd: number; monthly_limit_usd: number }
) {
  return request<Wallet>(`/wallets/${agentId}/configure`, {
    method: "POST", body: JSON.stringify(data),
  });
}

export async function freezeWallet(agentId: string) {
  return request(`/wallets/${agentId}/freeze`, { method: "POST" });
}

// ── Proxy ──

export async function executeProxy(data: any) {
  return request<any>("/proxy/execute", { method: "POST", body: JSON.stringify(data) });
}

// ── Audit ──

export async function getAuditLogs(params?: {
  agent_id?: string; hours?: number; limit?: number;
}) {
  const query = new URLSearchParams();
  if (params?.agent_id) query.set("agent_id", params.agent_id);
  if (params?.hours) query.set("hours", params.hours.toString());
  if (params?.limit) query.set("limit", params.limit.toString());
  return request<AuditEntry[]>(`/audit/logs?${query.toString()}`);
}

export async function verifyAuditChain() {
  return request<{ valid: boolean; checked: number; broken_at: number[] }>("/audit/verify-chain");
}

// ── Dashboard ──

export async function getDashboardStats() {
  return request<DashboardStats>("/dashboard/stats");
}

// ── HITL ──

export async function getPendingHITL() {
  return request<HITLItem[]>("/policies/hitl/pending");
}

export async function decideHITL(requestId: string, approved: boolean, note?: string) {
  return request(`/policies/hitl/${requestId}/decide`, {
    method: "POST", body: JSON.stringify({ approved, note: note || "" }),
  });
}