"use client";

import { Bot, Pause, Play, AlertTriangle } from "lucide-react";
import TrustGauge from "./TrustGauge";

interface Agent {
  id: string;
  name: string;
  agent_type: string;
  status: string;
  trust_score: number;
  identity_fingerprint: string;
}

interface Props {
  agent: Agent;
  onSuspend: (id: string) => void;
  onActivate: (id: string) => void;
  onClick: (id: string) => void;
}

const statusColors: Record<string, string> = {
  active: "bg-green-500/20 text-green-400 border-green-500/30",
  suspended: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  revoked: "bg-red-500/20 text-red-400 border-red-500/30",
  panic: "bg-red-600/30 text-red-300 border-red-500/50",
};

export default function AgentCard({ agent, onSuspend, onActivate, onClick }: Props) {
  return (
    <div
      className="bg-gray-900/60 border border-gray-800 rounded-xl p-5 hover:border-aegis-500/30
                 transition-all cursor-pointer glow-card group"
      onClick={() => onClick(agent.id)}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-aegis-600/10 border border-aegis-500/20
                        flex items-center justify-center group-hover:border-aegis-500/40 transition">
            <Bot size={20} className="text-aegis-400" />
          </div>
          <div>
            <h3 className="font-semibold text-white text-sm">{agent.name}</h3>
            <p className="text-xs text-gray-500 font-mono">{agent.agent_type}</p>
          </div>
        </div>
        <TrustGauge score={agent.trust_score} size={52} />
      </div>

      <div className="flex items-center justify-between">
        <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full border ${statusColors[agent.status] || statusColors.active}`}>
          {agent.status === "panic" && <AlertTriangle size={10} className="inline mr-1" />}
          {agent.status}
        </span>
        <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
          {agent.status === "active" ? (
            <button onClick={() => onSuspend(agent.id)}
              className="p-1.5 rounded-md hover:bg-yellow-500/10 text-gray-500 hover:text-yellow-400 transition"
              title="Suspend">
              <Pause size={14} />
            </button>
          ) : agent.status === "suspended" ? (
            <button onClick={() => onActivate(agent.id)}
              className="p-1.5 rounded-md hover:bg-green-500/10 text-gray-500 hover:text-green-400 transition"
              title="Activate">
              <Play size={14} />
            </button>
          ) : null}
        </div>
      </div>

      <p className="text-[9px] text-gray-600 font-mono mt-3 truncate">
        FP: {agent.identity_fingerprint}
      </p>
    </div>
  );
}