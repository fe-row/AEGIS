"use client";

import { useEffect, useState, useCallback } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { useToast } from "@/components/Toast";
import {
  getAgents, getPermissions, addPermission, getPendingHITL, decideHITL,
} from "@/lib/api";
import type { Agent, Permission, HITLItem } from "@/lib/types";
import { Plus, X, CheckCircle, XCircle, Clock, Shield, Loader2 } from "lucide-react";

export default function PoliciesPage() {
  const { toast } = useToast();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string>("");
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [hitlItems, setHitlItems] = useState<HITLItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddPerm, setShowAddPerm] = useState(false);
  const [permForm, setPermForm] = useState({
    service_name: "",
    allowed_actions: "read",
    max_requests_per_hour: 100,
    time_window_start: "00:00",
    time_window_end: "23:59",
    requires_hitl: false,
  });

  const fetchData = useCallback(async () => {
    try {
      const [agentList, hitl] = await Promise.all([getAgents(), getPendingHITL()]);
      setAgents(agentList);
      setHitlItems(hitl);
    } catch (err) {
      console.error("Failed to load policies data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchPermissions = useCallback(async (agentId: string) => {
    if (!agentId) return setPermissions([]);
    try {
      const perms = await getPermissions(agentId);
      setPermissions(perms);
    } catch (err) {
      console.error("Failed to load permissions:", err);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => { fetchPermissions(selectedAgent); }, [selectedAgent, fetchPermissions]);

  const handleAddPermission = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAgent) return;
    try {
      await addPermission(selectedAgent, {
        ...permForm,
        allowed_actions: permForm.allowed_actions.split(",").map((s) => s.trim()),
      });
      toast("Permission rule added", "success");
      setShowAddPerm(false);
      fetchPermissions(selectedAgent);
    } catch (err) {
      toast(err instanceof Error ? err.message : "Failed to add permission", "error");
    }
  };

  const handleHITLDecide = async (id: string, approved: boolean) => {
    try {
      await decideHITL(id, approved);
      toast(approved ? "Request approved" : "Request rejected", approved ? "success" : "warning");
      fetchData();
    } catch (err) {
      toast("Failed to process decision", "error");
    }
  };

  return (
    <DashboardLayout>
          <h1 className="text-2xl font-bold text-white mb-2">Policy Management</h1>
          <p className="text-sm text-gray-500 mb-8">Agent permissions and human-in-the-loop approvals</p>

          {loading ? (
            <div className="flex items-center justify-center py-24">
              <Loader2 className="w-8 h-8 text-aegis-500 animate-spin" />
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Permissions Panel */}
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold text-gray-200">Agent Permissions</h2>
                  {selectedAgent && (
                    <button
                      onClick={() => setShowAddPerm(true)}
                      className="flex items-center gap-1.5 bg-aegis-600 hover:bg-aegis-700 text-white
                               px-3 py-1.5 rounded-lg text-xs font-medium transition"
                    >
                      <Plus size={14} /> Add Rule
                    </button>
                  )}
                </div>

                <select
                  value={selectedAgent}
                  onChange={(e) => setSelectedAgent(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm mb-4
                           focus:outline-none focus:border-aegis-500 transition"
                >
                  <option value="">Select an agent...</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>{a.name} ({a.agent_type})</option>
                  ))}
                </select>

                <div className="space-y-3">
                  {permissions.map((perm) => (
                    <div key={perm.id}
                      className="bg-gray-900/60 border border-gray-800 rounded-xl p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Shield size={14} className="text-aegis-400" />
                          <span className="text-sm font-semibold text-white">{perm.service_name}</span>
                        </div>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${perm.is_active
                            ? "bg-green-500/10 text-green-400 border border-green-500/20"
                            : "bg-red-500/10 text-red-400 border border-red-500/20"
                          }`}>
                          {perm.is_active ? "ACTIVE" : "DISABLED"}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-xs text-gray-400">
                        <span>Actions: {perm.allowed_actions.join(", ")}</span>
                        <span>Rate: {perm.max_requests_per_hour}/hr</span>
                        <span>Window: {perm.time_window_start}—{perm.time_window_end}</span>
                        <span>HITL: {perm.requires_hitl ? "Yes" : "No"}</span>
                      </div>
                    </div>
                  ))}
                  {selectedAgent && permissions.length === 0 && (
                    <p className="text-center text-gray-600 py-8 text-sm">No permissions configured</p>
                  )}
                </div>
              </div>

              {/* HITL Panel */}
              <div>
                <h2 className="text-lg font-semibold text-gray-200 mb-4">
                  Pending Approvals
                  {hitlItems.length > 0 && (
                    <span className="ml-2 text-xs bg-orange-500/20 text-orange-400 px-2 py-0.5 rounded-full">
                      {hitlItems.length}
                    </span>
                  )}
                </h2>

                <div className="space-y-3">
                  {hitlItems.map((item) => (
                    <div key={item.id}
                      className="bg-gray-900/60 border border-orange-500/20 rounded-xl p-4">
                      <div className="flex items-start gap-3 mb-3">
                        <Clock size={16} className="text-orange-400 mt-0.5" />
                        <div className="flex-1">
                          <p className="text-sm text-gray-200">{item.action_description}</p>
                          <p className="text-xs text-gray-500 mt-1">
                            Cost: ${item.estimated_cost_usd.toFixed(4)} ·
                            Expires: {new Date(item.expires_at).toLocaleTimeString()}
                          </p>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button onClick={() => handleHITLDecide(item.id, true)}
                          className="flex-1 flex items-center justify-center gap-1.5 bg-green-600/10 hover:bg-green-600/20
                                   border border-green-500/20 text-green-400 py-1.5 rounded-lg text-xs font-medium transition">
                          <CheckCircle size={12} /> Approve
                        </button>
                        <button onClick={() => handleHITLDecide(item.id, false)}
                          className="flex-1 flex items-center justify-center gap-1.5 bg-red-600/10 hover:bg-red-600/20
                                   border border-red-500/20 text-red-400 py-1.5 rounded-lg text-xs font-medium transition">
                          <XCircle size={12} /> Reject
                        </button>
                      </div>
                    </div>
                  ))}
                  {hitlItems.length === 0 && (
                    <div className="text-center py-12 text-gray-600">
                      <CheckCircle size={32} className="mx-auto mb-3 text-green-600/40" />
                      <p className="text-sm">All clear — no pending approvals</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Add Permission Modal */}
          {showAddPerm && (
            <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
              <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-md p-6">
                <div className="flex items-center justify-between mb-5">
                  <h2 className="text-lg font-bold text-white">Add Permission Rule</h2>
                  <button onClick={() => setShowAddPerm(false)} className="text-gray-500 hover:text-gray-300">
                    <X size={20} />
                  </button>
                </div>
                <form onSubmit={handleAddPermission} className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1">Service Name</label>
                    <input
                      type="text" required value={permForm.service_name}
                      onChange={(e) => setPermForm({ ...permForm, service_name: e.target.value })}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm
                               focus:outline-none focus:border-aegis-500 transition"
                      placeholder="e.g., openai, stripe, salesforce"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1">Allowed Actions (comma-separated)</label>
                    <input
                      type="text" required value={permForm.allowed_actions}
                      onChange={(e) => setPermForm({ ...permForm, allowed_actions: e.target.value })}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm
                               focus:outline-none focus:border-aegis-500 transition"
                      placeholder="read, write"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-400 mb-1">Window Start</label>
                      <input type="time" value={permForm.time_window_start}
                        onChange={(e) => setPermForm({ ...permForm, time_window_start: e.target.value })}
                        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm
                                 focus:outline-none focus:border-aegis-500 transition" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-400 mb-1">Window End</label>
                      <input type="time" value={permForm.time_window_end}
                        onChange={(e) => setPermForm({ ...permForm, time_window_end: e.target.value })}
                        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm
                                 focus:outline-none focus:border-aegis-500 transition" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1">Max Requests/Hour</label>
                    <input type="number" value={permForm.max_requests_per_hour}
                      onChange={(e) => setPermForm({ ...permForm, max_requests_per_hour: parseInt(e.target.value) })}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm
                               focus:outline-none focus:border-aegis-500 transition" />
                  </div>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={permForm.requires_hitl}
                      onChange={(e) => setPermForm({ ...permForm, requires_hitl: e.target.checked })}
                      className="rounded bg-gray-800 border-gray-600 text-aegis-600 focus:ring-aegis-500" />
                    <span className="text-sm text-gray-300">Require Human Approval (HITL)</span>
                  </label>
                  <button type="submit"
                    className="w-full bg-aegis-600 hover:bg-aegis-700 text-white font-medium py-2.5 rounded-lg transition text-sm">
                    Add Permission
                  </button>
                </form>
              </div>
            </div>
          )}
    </DashboardLayout>
  );
}