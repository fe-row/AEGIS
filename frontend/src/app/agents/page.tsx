"use client";

import { useEffect, useState } from "react";
import Sidebar from "@/components/Sidebar";
import AgentCard from "@/components/AgentCard";
import { getAgents, createAgent, suspendAgent, activateAgent } from "@/lib/api";
import { Plus, X } from "lucide-react";

export default function AgentsPage() {
  const [agents, setAgents] = useState<any[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", agent_type: "general" });
  const [loading, setLoading] = useState(false);

  const fetchAgents = async () => {
    try {
      const data = await getAgents();
      setAgents(data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => { fetchAgents(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await createAgent(form);
      setShowCreate(false);
      setForm({ name: "", description: "", agent_type: "general" });
      fetchAgents();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSuspend = async (id: string) => {
    await suspendAgent(id);
    fetchAgents();
  };

  const handleActivate = async (id: string) => {
    await activateAgent(id);
    fetchAgents();
  };

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-y-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-white">Agent Registry</h1>
            <p className="text-sm text-gray-500 mt-1">Manage non-human identities</p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 bg-aegis-600 hover:bg-aegis-700 text-white
                     px-4 py-2.5 rounded-xl text-sm font-medium transition"
          >
            <Plus size={16} /> Register Agent
          </button>
        </div>

        {/* Agent Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              onSuspend={handleSuspend}
              onActivate={handleActivate}
              onClick={(id) => window.location.href = `/agents?detail=${id}`}
            />
          ))}
          {agents.length === 0 && (
            <div className="col-span-full text-center py-16 text-gray-600">
              <p className="text-lg mb-2">No agents registered yet</p>
              <p className="text-sm">Click "Register Agent" to create your first NHI</p>
            </div>
          )}
        </div>

        {/* Create Modal */}
        {showCreate && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-md p-6 shadow-2xl">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-lg font-bold text-white">Register New Agent</h2>
                <button onClick={() => setShowCreate(false)} className="text-gray-500 hover:text-gray-300">
                  <X size={20} />
                </button>
              </div>

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
            </div>
          </div>
        )}
      </main>
    </div>
  );
}