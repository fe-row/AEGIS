"use client";

import { LucideIcon } from "lucide-react";

interface Props {
  label: string;
  value: string | number;
  icon: LucideIcon;
  color: string;
  trend?: { value: number; positive: boolean };
}

export default function StatCard({ label, value, icon: Icon, color, trend }: Props) {
  return (
    <div className="bg-gray-900/60 border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition group">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-gray-500 font-medium uppercase tracking-wide">
          {label}
        </span>
        <Icon size={16} className={`${color} opacity-70 group-hover:opacity-100 transition`} />
      </div>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {trend && (
        <p className={`text-[10px] mt-1 ${trend.positive ? "text-green-400" : "text-red-400"}`}>
          {trend.positive ? "↑" : "↓"} {Math.abs(trend.value)}% vs yesterday
        </p>
      )}
    </div>
  );
}