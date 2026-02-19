"use client";

import { CheckCircle, XCircle } from "lucide-react";
import type { AuditEntry } from "@/lib/types";

interface Props {
  logs: AuditEntry[];
}

export default function AuditTable({ logs }: Props) {
  return (
    <div className="bg-gray-900/60 border border-gray-800 rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-500 text-xs uppercase">
              <th className="text-left px-4 py-3 font-medium">ID</th>
              <th className="text-left px-4 py-3 font-medium">Time</th>
              <th className="text-left px-4 py-3 font-medium">Action</th>
              <th className="text-left px-4 py-3 font-medium">Service</th>
              <th className="text-center px-4 py-3 font-medium">Granted</th>
              <th className="text-right px-4 py-3 font-medium">Cost</th>
              <th className="text-right px-4 py-3 font-medium">Status</th>
              <th className="text-right px-4 py-3 font-medium">Latency</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition">
                <td className="px-4 py-2.5 text-gray-400 font-mono text-xs">#{log.id}</td>
                <td className="px-4 py-2.5 text-gray-400 text-xs">
                  {new Date(log.timestamp).toLocaleTimeString()}
                </td>
                <td className="px-4 py-2.5">
                  <span className="text-xs font-mono bg-gray-800 px-2 py-0.5 rounded text-gray-300">
                    {log.action_type}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-gray-300 text-xs">{log.service_name || "—"}</td>
                <td className="px-4 py-2.5 text-center">
                  {log.permission_granted ? (
                    <CheckCircle size={16} className="text-green-500 inline" />
                  ) : (
                    <XCircle size={16} className="text-red-500 inline" />
                  )}
                </td>
                <td className="px-4 py-2.5 text-right text-xs text-gray-400">
                  ${log.cost_usd.toFixed(4)}
                </td>
                <td className="px-4 py-2.5 text-right text-xs">
                  <span className={
                    log.response_code && log.response_code < 400
                      ? "text-green-400" : "text-red-400"
                  }>
                    {log.response_code || "—"}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right text-xs text-gray-500">
                  {log.duration_ms ? `${log.duration_ms}ms` : "—"}
                </td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-600 text-sm">
                  No audit entries found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}