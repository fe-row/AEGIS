"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

interface DataPoint {
  hour: string;   // FIX: was "name" before
  spend: number;
  blocked: number;
}

interface Props {
  data: DataPoint[];
}

export default function SpendChart({ data }: Props) {
  if (!data || data.length === 0) {
    return (
      <div className="bg-gray-900/60 border border-gray-800 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">Spend & Blocked (24h)</h3>
        <div className="flex items-center justify-center h-[220px] text-gray-600 text-sm">
          No data yet
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-900/60 border border-gray-800 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-gray-300 mb-4">Spend & Blocked Actions (24h)</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} barGap={2}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          {/* FIX: dataKey changed from "name" to "hour" */}
          <XAxis
            dataKey="hour"
            tick={{ fontSize: 10, fill: "#6b7280" }}
            interval={3}
          />
          <YAxis tick={{ fontSize: 10, fill: "#6b7280" }} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#111827",
              border: "1px solid #374151",
              borderRadius: "8px",
              fontSize: 12,
            }}
            labelStyle={{ color: "#9ca3af" }}
          />
          <Bar dataKey="spend" fill="#4c6ef5" radius={[4, 4, 0, 0]} name="Spend ($)" />
          <Bar dataKey="blocked" fill="#ef4444" radius={[4, 4, 0, 0]} name="Blocked" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}