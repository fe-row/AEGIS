"use client";

import { useEffect, useState, useCallback } from "react";
import Sidebar from "@/components/Sidebar";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import AuditTable from "@/components/AuditTable";
import { getAuditLogs, verifyAuditChain, getAgents } from "@/lib/api";
import type { AuditEntry, Agent } from "@/lib/types";
import { ShieldCheck, ShieldAlert, RefreshCw, Loader2 } from "lucide-react";

interface ChainStatus {
  valid: boolean;
  checked: number;
  broken_at: number[];
}

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditEntry[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [chainStatus, setChainStatus] = useState<ChainStatus | null>(null);
  const [filters, setFilters] = useState({ agent_id: "", hours: 24, limit: 100 });
  const [loading, setLoading] = useState(false);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params: { hours: number; limit: number; agent_id?: string } = {
        hours: filters.hours,
        limit: filters.limit,
      };
      if (filters.agent_id) params.agent_id = filters.agent_id;
      const data = await getAuditLogs(params);
      setLogs(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  const fetchChainIntegrity = useCallback(async () => {
    try {
      const result = await verifyAuditChain();
      setChainStatus(result);
    } catch (err) {
      console.error(err);
    }
  }, []);

  useEffect(() => {
    getAgents().then(setAgents).catch(console.error);
    fetchChainIntegrity();
  }, [fetchChainIntegrity]);

  // Auto-apply: re-fetch logs whenever filters change
  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-y-auto">
        <ErrorBoundary>
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-2xl font-bold text-white">Forensic Audit Log</h1>
              <p className="text-sm text-gray-500 mt-1">Immutable, hash-chained activity record</p>
            </div>

            {/* Chain integrity badge */}
            <div className="flex items-center gap-4">
              {chainStatus && (
                <div className={`flex items-center gap-2 px-4 py-2 rounded-xl border text-sm font-medium ${chainStatus.valid
                    ? "bg-green-500/10 border-green-500/30 text-green-400"
                    : "bg-red-500/10 border-red-500/30 text-red-400"
                  }`}>
                  {chainStatus.valid ? <ShieldCheck size={16} /> : <ShieldAlert size={16} />}
                  Chain: {chainStatus.valid ? "INTACT" : "BROKEN"} ({chainStatus.checked} entries)
                </div>
              )}
              <button
                onClick={() => { fetchLogs(); fetchChainIntegrity(); }}
                disabled={loading}
                className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 transition"
              >
                <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
              </button>
            </div>
          </div>

          {/* Filters — auto-apply on change */}
          <div className="flex items-center gap-4 mb-6">
            <select
              value={filters.agent_id}
              onChange={(e) => setFilters({ ...filters, agent_id: e.target.value })}
              className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-sm
                       focus:outline-none focus:border-aegis-500 transition"
            >
              <option value="">All Agents</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>

            <select
              value={filters.hours}
              onChange={(e) => setFilters({ ...filters, hours: parseInt(e.target.value) })}
              className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-sm
                       focus:outline-none focus:border-aegis-500 transition"
            >
              <option value={1}>Last 1h</option>
              <option value={6}>Last 6h</option>
              <option value={24}>Last 24h</option>
              <option value={168}>Last 7d</option>
              <option value={720}>Last 30d</option>
            </select>

            {loading && (
              <Loader2 size={16} className="text-aegis-500 animate-spin" />
            )}
          </div>

          <AuditTable logs={logs} />
        </ErrorBoundary>
      </main>
    </div>
  );
}