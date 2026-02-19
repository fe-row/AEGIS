"use client";

import { useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import DashboardLayout from "@/components/DashboardLayout";
import SpendChart from "@/components/SpendChart";
import StatCard from "@/components/StatCard";
import HITLModal from "@/components/HITLModal";
import { StatGridSkeleton, ChartSkeleton } from "@/components/Skeleton";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useAuth } from "@/context/AuthContext";
import { useDashboardStats, usePendingHITL, queryKeys } from "@/hooks/useQueries";
import type { WSMessage } from "@/lib/types";
import {
  Bot, ShieldCheck, ShieldOff, Activity, Ban,
  DollarSign, TrendingUp, Bell, Wifi, WifiOff,
} from "lucide-react";

export default function DashboardPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [showHITL, setShowHITL] = useState(false);
  const [alerts, setAlerts] = useState<string[]>([]);

  const { data: stats, isLoading: statsLoading } = useDashboardStats();
  const { data: hitlItems = [] } = usePendingHITL();

  const invalidateDashboard = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    queryClient.invalidateQueries({ queryKey: queryKeys.hitl });
  }, [queryClient]);

  // WebSocket for real-time updates
  const handleWSMessage = useCallback((msg: WSMessage) => {
    switch (msg.event) {
      case "hitl_required":
        setAlerts((prev) => [...prev.slice(-4), `🔔 HITL required: ${msg.data.description}`]);
        invalidateDashboard();
        break;
      case "anomaly_detected":
        setAlerts((prev) => [...prev.slice(-4), `⚠️ Anomaly on agent ${msg.data.agent_id?.slice(0, 8)}`]);
        break;
      case "circuit_breaker":
        setAlerts((prev) => [...prev.slice(-4), `🚨 Circuit breaker: ${msg.data.status}`]);
        invalidateDashboard();
        break;
      case "hitl_decided":
        invalidateDashboard();
        break;
    }
  }, [invalidateDashboard]);

  const { connected } = useWebSocket(handleWSMessage);

  const cards = stats
    ? [
      { label: "Total Agents", value: stats.total_agents, icon: Bot, color: "text-aegis-500" },
      { label: "Active", value: stats.active_agents, icon: ShieldCheck, color: "text-green-400" },
      { label: "Suspended", value: stats.suspended_agents, icon: ShieldOff, color: "text-yellow-400" },
      { label: "Requests (24h)", value: stats.total_requests_24h.toLocaleString(), icon: Activity, color: "text-blue-400" },
      { label: "Blocked (24h)", value: stats.total_blocked_24h, icon: Ban, color: "text-red-400" },
      { label: "Spend (24h)", value: `$${stats.total_spend_24h.toFixed(2)}`, icon: DollarSign, color: "text-emerald-400" },
      { label: "Spend (Month)", value: `$${stats.total_spend_month.toFixed(2)}`, icon: TrendingUp, color: "text-purple-400" },
      { label: "Avg Trust", value: stats.avg_trust_score.toFixed(1), icon: ShieldCheck, color: "text-cyan-400" },
    ]
    : [];

  return (
    <DashboardLayout>
          {/* Header */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-2xl font-bold text-white">Mission Control</h1>
              <p className="text-sm text-gray-500 mt-1">
                Welcome back, {user?.full_name || "Operator"}
              </p>
            </div>
            <div className="flex items-center gap-3">
              {/* WS status */}
              <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-medium border ${connected
                  ? "bg-green-500/10 border-green-500/20 text-green-400"
                  : "bg-red-500/10 border-red-500/20 text-red-400"
                }`}>
                {connected ? <Wifi size={10} /> : <WifiOff size={10} />}
                {connected ? "LIVE" : "OFFLINE"}
              </div>

              {stats && stats.pending_hitl > 0 && (
                <button
                  onClick={() => setShowHITL(true)}
                  className="flex items-center gap-2 bg-orange-500/10 hover:bg-orange-500/20
                           border border-orange-500/30 text-orange-400 px-4 py-2 rounded-xl
                           text-sm font-medium transition animate-pulse"
                >
                  <Bell size={16} />
                  {stats.pending_hitl} Pending
                </button>
              )}
            </div>
          </div>

          {/* Real-time alerts */}
          {alerts.length > 0 && (
            <div className="mb-6 space-y-2">
              {alerts.map((alert, i) => (
                <div
                  key={i}
                  className="bg-gray-900/80 border border-aegis-500/20 text-gray-300
                           px-4 py-2 rounded-lg text-sm animate-in slide-in-from-right"
                >
                  {alert}
                </div>
              ))}
            </div>
          )}

          {/* Stats */}
          {!stats ? (
            <div className="mb-8"><StatGridSkeleton /></div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
              {cards.map((card) => (
                <StatCard key={card.label} {...card} />
              ))}
            </div>
          )}

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            {!stats ? <ChartSkeleton /> : <SpendChart data={stats.hourly_spend || []} />}

            {/* Top Services */}
            <div className="bg-gray-900/60 border border-gray-800 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-gray-300 mb-4">Top Services (24h)</h3>
              <div className="space-y-3">
                {(stats?.top_services || []).map((svc) => (
                  <div key={svc.service} className="flex items-center justify-between">
                    <div>
                      <span className="text-sm text-gray-200 font-medium">{svc.service}</span>
                      <span className="text-xs text-gray-500 ml-2">{svc.requests} req</span>
                    </div>
                    <span className="text-xs font-mono text-emerald-400">${svc.cost.toFixed(4)}</span>
                  </div>
                ))}
                {(!stats?.top_services || stats.top_services.length === 0) && (
                  <p className="text-sm text-gray-600 text-center py-4">No service activity yet</p>
                )}
              </div>
            </div>
          </div>

          {showHITL && (
            <HITLModal
              items={hitlItems}
              onDecided={() => { invalidateDashboard(); setShowHITL(false); }}
              onClose={() => setShowHITL(false)}
            />
          )}
    </DashboardLayout>
  );
}