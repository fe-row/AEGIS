"use client";

import { useState } from "react";
import { ShieldAlert, CheckCircle, XCircle, X } from "lucide-react";
import { decideHITL } from "@/lib/api";
import type { HITLItem } from "@/lib/types";

interface Props {
  items: HITLItem[];
  onDecided: () => void;
  onClose: () => void;
}

export default function HITLModal({ items, onDecided, onClose }: Props) {
  const [loading, setLoading] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const handleDecide = async (id: string, approved: boolean) => {
    setLoading(id);
    try {
      await decideHITL(id, approved, notes[id] || "");
      onDecided();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(null);
      setNotes((prev) => { const next = { ...prev }; delete next[id]; return next; });
    }
  };

  if (items.length === 0) return null;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-orange-500/10 border border-orange-500/30 flex items-center justify-center">
              <ShieldAlert size={20} className="text-orange-400" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">Pending Approvals</h2>
              <p className="text-xs text-gray-500">{items.length} action(s) require human authorization</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 transition">
            <X size={20} />
          </button>
        </div>

        {/* Items */}
        <div className="overflow-y-auto max-h-[55vh] p-5 space-y-4">
          {items.map((item) => (
            <div key={item.id} className="bg-gray-800/60 border border-gray-700 rounded-xl p-4">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <p className="text-sm text-gray-200 font-medium">{item.action_description}</p>
                  <p className="text-xs text-gray-500 mt-1 font-mono">Agent: {item.agent_id.slice(0, 8)}...</p>
                </div>
                <span className="text-sm font-bold text-orange-400">${item.estimated_cost_usd.toFixed(4)}</span>
              </div>

              <div className="flex items-center gap-2 text-[10px] text-gray-500 mb-3">
                <span>Created: {new Date(item.created_at).toLocaleString()}</span>
                <span>·</span>
                <span>Expires: {new Date(item.expires_at).toLocaleString()}</span>
              </div>

              <input
                type="text"
                placeholder="Optional note..."
                value={notes[item.id] || ""}
                onChange={(e) => setNotes((prev) => ({ ...prev, [item.id]: e.target.value }))}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-xs
                         text-gray-300 mb-3 focus:outline-none focus:border-aegis-500"
              />

              <div className="flex gap-2">
                <button
                  onClick={() => handleDecide(item.id, true)}
                  disabled={loading === item.id}
                  className="flex-1 flex items-center justify-center gap-2 bg-green-600/20 hover:bg-green-600/30
                           border border-green-500/30 text-green-400 py-2 rounded-lg text-xs font-medium transition"
                >
                  <CheckCircle size={14} /> Approve
                </button>
                <button
                  onClick={() => handleDecide(item.id, false)}
                  disabled={loading === item.id}
                  className="flex-1 flex items-center justify-center gap-2 bg-red-600/20 hover:bg-red-600/30
                           border border-red-500/30 text-red-400 py-2 rounded-lg text-xs font-medium transition"
                >
                  <XCircle size={14} /> Reject
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}