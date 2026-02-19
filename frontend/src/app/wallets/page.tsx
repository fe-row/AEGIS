"use client";

import { useEffect, useState, useCallback } from "react";
import Sidebar from "@/components/Sidebar";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { getAgents, getWallet, topUpWallet, freezeWallet } from "@/lib/api";
import type { Agent, Wallet } from "@/lib/types";
import { Wallet as WalletIcon, Snowflake, Plus, Loader2 } from "lucide-react";

export default function WalletsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [wallets, setWallets] = useState<Record<string, Wallet>>({});
  const [topUpAgent, setTopUpAgent] = useState<string | null>(null);
  const [topUpAmount, setTopUpAmount] = useState("");
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const agentList = await getAgents();
      setAgents(agentList);
      const walletMap: Record<string, Wallet> = {};
      await Promise.all(agentList.map(async (a: Agent) => {
        try {
          walletMap[a.id] = await getWallet(a.id);
        } catch { /* no wallet */ }
      }));
      setWallets(walletMap);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleTopUp = async () => {
    if (!topUpAgent || !topUpAmount) return;
    try {
      await topUpWallet(topUpAgent, parseFloat(topUpAmount));
      setTopUpAgent(null);
      setTopUpAmount("");
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleFreeze = async (agentId: string) => {
    if (confirm("Freeze this wallet? The agent will not be able to spend.")) {
      await freezeWallet(agentId);
      fetchData();
    }
  };

  const agentsWithWallets = agents.filter((a) => wallets[a.id]);

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-y-auto">
        <ErrorBoundary>
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-white">Micro-Wallets</h1>
            <p className="text-sm text-gray-500 mt-1">Per-agent financial controls and FinOps</p>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-24">
              <Loader2 className="w-8 h-8 text-aegis-500 animate-spin" />
            </div>
          ) : agentsWithWallets.length === 0 ? (
            <div className="text-center py-24 text-gray-600">
              <WalletIcon size={40} className="mx-auto mb-4 text-gray-700" />
              <p className="text-lg mb-1">No wallets found</p>
              <p className="text-sm">Wallets are created automatically when agents are registered</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {agentsWithWallets.map((agent) => {
                const w = wallets[agent.id];

                const balancePct = w.daily_limit_usd > 0
                  ? (w.spent_today_usd / w.daily_limit_usd) * 100
                  : 0;

                return (
                  <div key={agent.id}
                    className="bg-gray-900/60 border border-gray-800 rounded-xl p-5 hover:border-gray-700 transition">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-emerald-600/10 border border-emerald-500/20
                                      flex items-center justify-center">
                          <WalletIcon size={18} className="text-emerald-400" />
                        </div>
                        <div>
                          <h3 className="text-sm font-semibold text-white">{agent.name}</h3>
                          <p className="text-[10px] text-gray-500 font-mono">{agent.agent_type}</p>
                        </div>
                      </div>
                      {w.is_frozen && (
                        <span className="text-[10px] font-bold text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded-full
                                       border border-blue-500/20 flex items-center gap-1">
                          <Snowflake size={10} /> FROZEN
                        </span>
                      )}
                    </div>

                    {/* Balance */}
                    <div className="text-center mb-4">
                      <p className="text-3xl font-bold text-white">${w.balance_usd.toFixed(2)}</p>
                      <p className="text-[10px] text-gray-500 uppercase mt-1">Available Balance</p>
                    </div>

                    {/* Daily spend bar */}
                    <div className="mb-3">
                      <div className="flex justify-between text-[10px] text-gray-500 mb-1">
                        <span>Daily: ${w.spent_today_usd.toFixed(2)} / ${w.daily_limit_usd.toFixed(2)}</span>
                        <span>{balancePct.toFixed(0)}%</span>
                      </div>
                      <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${balancePct > 80 ? "bg-red-500" : balancePct > 50 ? "bg-yellow-500" : "bg-emerald-500"
                            }`}
                          style={{ width: `${Math.min(balancePct, 100)}%` }}
                        />
                      </div>
                    </div>

                    <p className="text-[10px] text-gray-500 mb-4">
                      Monthly: ${w.spent_this_month_usd.toFixed(2)} / ${w.monthly_limit_usd.toFixed(2)}
                    </p>

                    {/* Actions */}
                    <div className="flex gap-2">
                      <button
                        onClick={() => setTopUpAgent(agent.id)}
                        className="flex-1 flex items-center justify-center gap-1.5 bg-emerald-600/10 hover:bg-emerald-600/20
                                 border border-emerald-500/20 text-emerald-400 py-2 rounded-lg text-xs font-medium transition"
                      >
                        <Plus size={12} /> Top Up
                      </button>
                      {!w.is_frozen && (
                        <button
                          onClick={() => handleFreeze(agent.id)}
                          className="flex-1 flex items-center justify-center gap-1.5 bg-blue-600/10 hover:bg-blue-600/20
                                   border border-blue-500/20 text-blue-400 py-2 rounded-lg text-xs font-medium transition"
                        >
                          <Snowflake size={12} /> Freeze
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Top-up modal */}
          {topUpAgent && (
            <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
              <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-sm p-6">
                <h2 className="text-lg font-bold text-white mb-4">Top Up Wallet</h2>
                <input
                  type="number" step="0.01" min="0.01" value={topUpAmount}
                  onChange={(e) => setTopUpAmount(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm mb-4
                           focus:outline-none focus:border-aegis-500 transition"
                  placeholder="Amount (USD)"
                />
                <div className="flex gap-2">
                  <button onClick={handleTopUp}
                    className="flex-1 bg-aegis-600 hover:bg-aegis-700 text-white py-2.5 rounded-lg text-sm font-medium transition">
                    Confirm
                  </button>
                  <button onClick={() => setTopUpAgent(null)}
                    className="flex-1 bg-gray-800 hover:bg-gray-700 text-gray-300 py-2.5 rounded-lg text-sm font-medium transition">
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}
        </ErrorBoundary>
      </main>
    </div>
  );
}