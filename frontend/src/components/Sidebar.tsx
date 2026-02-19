"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Shield, Bot, ScrollText, Wallet, BarChart3, FileCheck, LogOut, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { logout } from "@/lib/api";
import clsx from "clsx";

const nav = [
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/policies", label: "Policies & HITL", icon: FileCheck },
  { href: "/wallets", label: "Wallets", icon: Wallet },
  { href: "/audit", label: "Audit Log", icon: ScrollText },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside className={clsx(
      "bg-gray-900 border-r border-gray-800 min-h-screen flex flex-col transition-all duration-300",
      collapsed ? "w-[68px]" : "w-64"
    )}>
      {/* Logo */}
      <div className="p-4 border-b border-gray-800">
        <Link href="/dashboard" className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-aegis-600/20 border border-aegis-500/30 flex items-center justify-center shrink-0">
            <Shield className="w-5 h-5 text-aegis-500" />
          </div>
          {!collapsed && (
            <div className="overflow-hidden">
              <h1 className="text-lg font-bold text-white tracking-tight">AEGIS</h1>
              <p className="text-[10px] text-gray-500 uppercase tracking-widest">Agentic IAM</p>
            </div>
          )}
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-3 space-y-1">
        {nav.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={clsx(
                "flex items-center gap-3 rounded-lg text-sm font-medium transition-all",
                collapsed ? "px-3 py-2.5 justify-center" : "px-4 py-2.5",
                active
                  ? "bg-aegis-600/20 text-aegis-200 border border-aegis-500/20"
                  : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60 border border-transparent"
              )}
            >
              <item.icon size={18} className="shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-gray-800 space-y-1">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className={clsx(
            "flex items-center gap-3 rounded-lg text-sm font-medium transition w-full",
            collapsed ? "px-3 py-2 justify-center" : "px-4 py-2",
            "text-gray-600 hover:text-gray-400 hover:bg-gray-800/60"
          )}
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          {!collapsed && <span className="text-xs">Collapse</span>}
        </button>
        <button
          onClick={logout}
          title={collapsed ? "Sign Out" : undefined}
          className={clsx(
            "flex items-center gap-3 rounded-lg text-sm font-medium transition w-full",
            collapsed ? "px-3 py-2.5 justify-center" : "px-4 py-2.5",
            "text-gray-500 hover:text-red-400 hover:bg-red-500/10"
          )}
        >
          <LogOut size={18} className="shrink-0" />
          {!collapsed && <span>Sign Out</span>}
        </button>
      </div>
    </aside>
  );
}