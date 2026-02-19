"use client";

import { useEffect, useState, useMemo } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import AgentCard from "@/components/AgentCard";
import AgentDetailPanel from "@/components/AgentDetailPanel";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { getAgents, createAgent, suspendAgent, activateAgent } from "@/lib/api";
import type { Agent } from "@/lib/types";
import { Plus, Search, Bot, Loader2 } from "lucide-react";

export default function AgentsPage() {
  const { toast } = useToast();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", agent_type: "general" });
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  // Search & filter
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const filteredAgents = useMemo(() => {
    return agents.filter((a) => {
      const matchesSearch = !search ||
        a.name.toLowerCase().includes(search.toLowerCase()) ||
        a.agent_type.toLowerCase().includes(search.toLowerCase()) ||
        a.description?.toLowerCase().includes(search.toLowerCase());
      const matchesStatus = statusFilter === "all" || a.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [agents, search, statusFilter]);

  const fetchAgents = async () => {
    try {
      const data = await getAgents();
      setAgents(data);
    } catch (err) {
      toast("Failed to load agents", "error");
    } finally {
      setInitialLoading(false);
    }
  };

  useEffect(() => { fetchAgents(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await createAgent(form);
      toast(`Agent "${form.name}" registered successfully`, "success");
      setShowCreate(false);
      setForm({ name: "", description: "", agent_type: "general" });
      fetchAgents();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Failed to create agent", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleSuspend = async (id: string) => {
    try {
      await suspendAgent(id);
      toast("Agent suspended", "warning");
      fetchAgents();
    } catch (err) {
      toast("Failed to suspend agent", "error");
    }
  };

  const handleActivate = async (id: string) => {
    try {
      await activateAgent(id);
      toast("Agent activated", "success");
      fetchAgents();
    } catch (err) {
      toast("Failed to activate agent", "error");
    }
  };

  return (
    <DashboardLayout>
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-white">Agent Registry</h1>
              <p className="text-sm text-gray-500 mt-1">
                Manage non-human identities
                {agents.length > 0 && <span className="text-gray-600 ml-1">({agents.length} total)</span>}
              </p>
            </div>
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-2 bg-aegis-600 hover:bg-aegis-700 text-white
                     px-4 py-2.5 rounded-xl text-sm font-medium transition"
            >
              <Plus size={16} /> Register Agent
            </button>
          </div>

          {/* Search & Filter Bar */}
          <div className="flex items-center gap-3 mb-6">
            <div className="relative flex-1 max-w-sm">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search agents..."
                className="w-full bg-gray-800/60 border border-gray-700 rounded-lg pl-9 pr-4 py-2 text-sm
                         text-gray-300 focus:outline-none focus:border-aegis-500 transition placeholder:text-gray-600"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-gray-800/60 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-300
                       focus:outline-none focus:border-aegis-500 transition"
            >
              <option value="all">All Status</option>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
              <option value="revoked">Revoked</option>
              <option value="panic">Panic</option>
            </select>
          </div>

          {/* Agent Grid */}
          {initialLoading ? (
            <div className="flex items-center justify-center py-24">
              <Loader2 className="w-8 h-8 text-aegis-500 animate-spin" />
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredAgents.map((agent) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  onSuspend={handleSuspend}
                  onActivate={handleActivate}
                  onClick={(id) => setSelectedAgentId(id)}
                />
              ))}
              {filteredAgents.length === 0 && agents.length > 0 && (
                <div className="col-span-full text-center py-16 text-gray-600">
                  <Search size={32} className="mx-auto mb-3 text-gray-700" />
                  <p className="text-sm">No agents match your search</p>
                </div>
              )}
              {agents.length === 0 && (
                <div className="col-span-full text-center py-16 text-gray-600">
                  <Bot size={40} className="mx-auto mb-3 text-gray-700" />
                  <p className="text-lg mb-2">No agents registered yet</p>
                  <p className="text-sm">Click "Register Agent" to create your first NHI</p>
                </div>
              )}
            </div>
          )}

          {/* Agent Detail Slide-over */}
          {selectedAgentId && (
            <AgentDetailPanel
              agentId={selectedAgentId}
              onClose={() => setSelectedAgentId(null)}
            />
          )}

          {/* Create Modal */}
          <Modal
            open={showCreate}
            onClose={() => setShowCreate(false)}
            title="Register New Agent"
            icon={<div className="w-10 h-10 rounded-xl bg-aegis-600/20 border border-aegis-500/30 flex items-center justify-center"><Bot size={18} className="text-aegis-400" /></div>}
          >
                <form onSubmit={handleCreate} className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1">Agent Name</label>
                    <input
                      type="text" required value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm
                             focus:outline-none focus:border-aegis-500 transition"
                      placeholder="e.g., Sales_CRM_Bot"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1">Agent Type</label>
                    <select
                      value={form.agent_type}
                      onChange={(e) => setForm({ ...form, agent_type: e.target.value })}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm
                             focus:outline-none focus:border-aegis-500 transition"
                    >
                      <option value="general">General</option>
                      <option value="sales">Sales</option>
                      <option value="support">Customer Support</option>
                      <option value="devops">DevOps</option>
                      <option value="analytics">Analytics</option>
                      <option value="hr">Human Resources</option>
                      <option value="finance">Finance</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1">Description</label>
                    <textarea
                      value={form.description}
                      onChange={(e) => setForm({ ...form, description: e.target.value })}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm
                             focus:outline-none focus:border-aegis-500 transition resize-none"
                      rows={3}
                      placeholder="What does this agent do?"
                    />
                  </div>

                  <button
                    type="submit" disabled={loading}
                    className="w-full bg-aegis-600 hover:bg-aegis-700 disabled:opacity-50 text-white
                           font-medium py-2.5 rounded-lg transition text-sm"
                  >
                    {loading ? "Creating..." : "Register Agent"}
                  </button>
                </form>
          </Modal>
    </DashboardLayout>
  );
}