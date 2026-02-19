"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getDashboardStats,
  getAgents,
  getAgent,
  getWallet,
  getAuditLogs,
  getPendingHITL,
  createAgent,
  suspendAgent,
  activateAgent,
  topUpWallet,
  freezeWallet,
  configureWallet,
  decideHITL,
  executeProxy,
} from "@/lib/api";
import type { ProxyRequest } from "@/lib/types";

// ── Query keys ──

export const queryKeys = {
  dashboard: ["dashboard"] as const,
  agents: ["agents"] as const,
  agent: (id: string) => ["agents", id] as const,
  wallet: (agentId: string) => ["wallets", agentId] as const,
  audit: (params?: Record<string, unknown>) => ["audit", params] as const,
  hitl: ["hitl"] as const,
};

// ── Queries ──

export function useDashboardStats(opts?: { refetchInterval?: number }) {
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: getDashboardStats,
    refetchInterval: opts?.refetchInterval ?? 30_000,
  });
}

export function useAgents() {
  return useQuery({
    queryKey: queryKeys.agents,
    queryFn: getAgents,
  });
}

export function useAgent(id: string) {
  return useQuery({
    queryKey: queryKeys.agent(id),
    queryFn: () => getAgent(id),
    enabled: !!id,
  });
}

export function useWallet(agentId: string) {
  return useQuery({
    queryKey: queryKeys.wallet(agentId),
    queryFn: () => getWallet(agentId),
    enabled: !!agentId,
  });
}

export function useAuditLogs(params?: {
  agent_id?: string;
  hours?: number;
  limit?: number;
}) {
  return useQuery({
    queryKey: queryKeys.audit(params as Record<string, unknown>),
    queryFn: () => getAuditLogs(params),
  });
}

export function usePendingHITL() {
  return useQuery({
    queryKey: queryKeys.hitl,
    queryFn: getPendingHITL,
    refetchInterval: 15_000,
  });
}

// ── Mutations ──

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; description: string; agent_type: string }) =>
      createAgent(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.agents });
      qc.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useSuspendAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => suspendAgent(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.agents });
      qc.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useActivateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => activateAgent(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.agents });
      qc.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useTopUpWallet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, amount }: { agentId: string; amount: number }) =>
      topUpWallet(agentId, amount),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.wallet(vars.agentId) });
      qc.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useFreezeWallet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (agentId: string) => freezeWallet(agentId),
    onSuccess: (_data, agentId) => {
      qc.invalidateQueries({ queryKey: queryKeys.wallet(agentId) });
    },
  });
}

export function useConfigureWallet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      agentId,
      data,
    }: {
      agentId: string;
      data: { daily_limit_usd: number; monthly_limit_usd: number };
    }) => configureWallet(agentId, data),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.wallet(vars.agentId) });
    },
  });
}

export function useDecideHITL() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      requestId,
      approved,
      note,
    }: {
      requestId: string;
      approved: boolean;
      note?: string;
    }) => decideHITL(requestId, approved, note),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.hitl });
      qc.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useExecuteProxy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ProxyRequest) => executeProxy(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.dashboard });
      qc.invalidateQueries({ queryKey: queryKeys.audit() });
    },
  });
}
