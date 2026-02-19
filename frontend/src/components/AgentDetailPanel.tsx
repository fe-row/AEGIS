"use client";

import { useEffect, useState } from "react";
import { X, Bot, Key, Shield, Plus, Trash2, Loader2, Copy, Check } from "lucide-react";
import TrustGauge from "./TrustGauge";
import Modal from "./Modal";
import { useToast } from "./Toast";
import { getAgent, getPermissions, getWallet, storeSecret, addPermission, deletePermission } from "@/lib/api";
import type { Agent, Permission, Wallet } from "@/lib/types";

interface Props {
  agentId: string;
  onClose: () => void;
}

export default function AgentDetailPanel({ agentId, onClose }: Props) {
  const { toast } = useToast();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [perms, setPerms] = useState<Permission[]>([]);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  // Secret form
  const [showSecretForm, setShowSecretForm] = useState(false);
  const [secretForm, setSecretForm] = useState({ service_name: "", secret_value: "" });

  // Permission form
  const [showPermForm, setShowPermForm] = useState(false);
  const [permForm, setPermForm] = useState({
    service_name: "",
    allowed_actions: "read",
    max_requests_per_hour: 100,
    time_window_start: "00:00",
    time_window_end: "23:59",
    requires_hitl: false,
  });

  const fetchData = async () => {
    try {
      const [a, p] = await Promise.all([getAgent(agentId), getPermissions(agentId)]);
      setAgent(a);
      setPerms(p);
      try {
        const w = await getWallet(agentId);
        setWallet(w);
      } catch { /* no wallet */ }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [agentId]);

  const handleCopyId = () => {
    navigator.clipboard.writeText(agentId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleStoreSecret = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await storeSecret(agentId, secretForm);
      toast("Secret stored securely", "success");
      setShowSecretForm(false);
      setSecretForm({ service_name: "", secret_value: "" });
    } catch (err) {
      toast(err instanceof Error ? err.message : "Failed to store secret", "error");
    }
  };

  const handleAddPerm = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await addPermission(agentId, {
        ...permForm,
        allowed_actions: permForm.allowed_actions.split(",").map((s) => s.trim()),
        max_records_per_request: 100,
      });
      toast("Permission added", "success");
      setShowPermForm(false);
      setPermForm({
        service_name: "",
        allowed_actions: "read",
        max_requests_per_hour: 100,
        time_window_start: "00:00",
        time_window_end: "23:59",
        requires_hitl: false,
      });
      fetchData();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Failed to add permission", "error");
    }
  };

  const handleDeletePerm = async (permId: string) => {
    try {
      await deletePermission(agentId, permId);
      toast("Permission removed", "success");
      fetchData();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Failed to remove permission", "error");
    }
  };

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-aegis-500 animate-spin" />
      </div>
    );
  }

  if (!agent) return null;

  const statusColors: Record<string, string> = {
    active: "bg-green-500/20 text-green-400 border-green-500/30",
    suspended: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    revoked: "bg-red-500/20 text-red-400 border-red-500/30",
    panic: "bg-red-600/30 text-red-300 border-red-500/50",
  };

  return (
    <>
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 animate-fade-in"
        onClick={onClose}
      />
      <div className="fixed top-0 right-0 h-full w-full max-w-lg bg-gray-900 border-l border-gray-800 z-50 overflow-y-auto animate-slide-in-right shadow-2xl">
        {/* Header */}
        <div className="sticky top-0 bg-gray-900/95 backdrop-blur-sm border-b border-gray-800 p-5 z-10">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-aegis-600/10 border border-aegis-500/20 flex items-center justify-center">
                <Bot size={20} className="text-aegis-400" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-white">{agent.name}</h2>
                <p className="text-xs text-gray-500 font-mono">{agent.agent_type}</p>
              </div>
            </div>
            <button onClick={onClose} className="text-gray-500 hover:text-gray-300 p-1.5 rounded-lg hover:bg-gray-800 transition">
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="p-5 space-y-6">
          {/* Status + Trust */}
          <div className="flex items-center justify-between">
            <span className={`text-[10px] uppercase font-bold px-2.5 py-1 rounded-full border ${statusColors[agent.status] || statusColors.active}`}>
              {agent.status}
            </span>
            <TrustGauge score={agent.trust_score} size={64} />
          </div>

          {/* Agent ID */}
          <div className="bg-gray-800/60 rounded-xl p-4">
            <p className="text-[10px] text-gray-500 uppercase font-medium mb-1">Agent ID</p>
            <div className="flex items-center gap-2">
              <code className="text-xs text-gray-300 font-mono flex-1 truncate">{agentId}</code>
              <button onClick={handleCopyId} className="text-gray-500 hover:text-gray-300 transition">
                {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
              </button>
            </div>
            <p className="text-[10px] text-gray-600 font-mono mt-2 truncate">
              FP: {agent.identity_fingerprint}
            </p>
          </div>

          {/* Wallet summary */}
          {wallet && (
            <div className="bg-gray-800/60 rounded-xl p-4">
              <p className="text-[10px] text-gray-500 uppercase font-medium mb-2">Wallet</p>
              <div className="grid grid-cols-3 gap-3 text-center">
                <div>
                  <p className="text-lg font-bold text-white">${wallet.balance_usd.toFixed(2)}</p>
                  <p className="text-[10px] text-gray-500">Balance</p>
                </div>
                <div>
                  <p className="text-lg font-bold text-emerald-400">${wallet.spent_today_usd.toFixed(2)}</p>
                  <p className="text-[10px] text-gray-500">Today</p>
                </div>
                <div>
                  <p className="text-lg font-bold text-purple-400">${wallet.spent_this_month_usd.toFixed(2)}</p>
                  <p className="text-[10px] text-gray-500">Month</p>
                </div>
              </div>
            </div>
          )}

          {/* Permissions */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
                <Shield size={14} className="text-aegis-400" />
                Permissions ({perms.length})
              </h3>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowSecretForm(true)}
                  className="flex items-center gap-1 text-[10px] font-medium text-gray-400 hover:text-aegis-300 transition px-2 py-1 rounded-lg hover:bg-gray-800"
                >
                  <Key size={12} /> Secret
                </button>
                <button
                  onClick={() => setShowPermForm(true)}
                  className="flex items-center gap-1 text-[10px] font-medium text-aegis-400 hover:text-aegis-300 transition px-2 py-1 rounded-lg hover:bg-aegis-600/10"
                >
                  <Plus size={12} /> Add
                </button>
              </div>
            </div>

            <div className="space-y-2">
              {perms.map((perm) => (
                <div key={perm.id} className="bg-gray-800/40 border border-gray-800 rounded-lg p-3 group">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-white">{perm.service_name}</span>
                    <div className="flex items-center gap-2">
                      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${perm.is_active ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}>
                        {perm.is_active ? "ON" : "OFF"}
                      </span>
                      <button
                        onClick={() => handleDeletePerm(perm.id)}
                        className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 transition"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-gray-500">
                    <span>{perm.allowed_actions.join(", ")}</span>
                    <span>{perm.max_requests_per_hour}/hr</span>
                    <span>{perm.time_window_start}—{perm.time_window_end}</span>
                    {perm.requires_hitl && <span className="text-orange-400">HITL</span>}
                  </div>
                </div>
              ))}
              {perms.length === 0 && (
                <p className="text-center text-gray-600 text-xs py-4">No permissions configured</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Store Secret Modal */}
      <Modal open={showSecretForm} onClose={() => setShowSecretForm(false)} title="Store Secret" icon={<Key size={18} className="text-aegis-400" />}>
        <form onSubmit={handleStoreSecret} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Service Name</label>
            <input
              type="text" required value={secretForm.service_name}
              onChange={(e) => setSecretForm({ ...secretForm, service_name: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-aegis-500 transition"
              placeholder="e.g., openai"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Secret Value</label>
            <input
              type="password" required value={secretForm.secret_value}
              onChange={(e) => setSecretForm({ ...secretForm, secret_value: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-aegis-500 transition"
              placeholder="sk-..."
            />
          </div>
          <button type="submit" className="w-full bg-aegis-600 hover:bg-aegis-700 text-white font-medium py-2.5 rounded-lg transition text-sm">
            Store Securely
          </button>
        </form>
      </Modal>

      {/* Add Permission Modal */}
      <Modal open={showPermForm} onClose={() => setShowPermForm(false)} title="Add Permission" icon={<Shield size={18} className="text-aegis-400" />}>
        <form onSubmit={handleAddPerm} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Service</label>
            <input
              type="text" required value={permForm.service_name}
              onChange={(e) => setPermForm({ ...permForm, service_name: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-aegis-500 transition"
              placeholder="e.g., openai, stripe"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Actions (comma-separated)</label>
            <input
              type="text" required value={permForm.allowed_actions}
              onChange={(e) => setPermForm({ ...permForm, allowed_actions: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-aegis-500 transition"
              placeholder="read, write"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Max Requests/Hour</label>
            <input
              type="number" value={permForm.max_requests_per_hour}
              onChange={(e) => setPermForm({ ...permForm, max_requests_per_hour: parseInt(e.target.value) })}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-aegis-500 transition"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Start</label>
              <input type="time" value={permForm.time_window_start}
                onChange={(e) => setPermForm({ ...permForm, time_window_start: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-aegis-500 transition" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">End</label>
              <input type="time" value={permForm.time_window_end}
                onChange={(e) => setPermForm({ ...permForm, time_window_end: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-aegis-500 transition" />
            </div>
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={permForm.requires_hitl}
              onChange={(e) => setPermForm({ ...permForm, requires_hitl: e.target.checked })}
              className="rounded bg-gray-800 border-gray-600 text-aegis-600 focus:ring-aegis-500" />
            <span className="text-sm text-gray-300">Require HITL</span>
          </label>
          <button type="submit" className="w-full bg-aegis-600 hover:bg-aegis-700 text-white font-medium py-2.5 rounded-lg transition text-sm">
            Add Permission
          </button>
        </form>
      </Modal>
    </>
  );
}
