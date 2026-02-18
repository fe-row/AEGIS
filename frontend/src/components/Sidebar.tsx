"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Shield, Bot, ScrollText, Wallet, BarChart3, FileCheck, LogOut } from "lucide-react";
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

  return (
    <aside className="w-64 bg-gray-900 border-r border-gray-800 min-h-screen flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-gray-800">
        <Link href="/dashboard" className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-aegis-600/20 border border-aegis-500/30 flex items-center justify-center">
            <Shield className="w-5 h-5 text-aegis-500" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white tracking-tight">AEGIS</h1>
            <p className="text-[10px] text-gray-500 uppercase tracking-widest">Agentic IAM</p>
          </div>
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-4 space-y-1">
        {nav.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all",
                active
                  ? "bg-aegis-600/20 text-aegis-200 border border-aegis-500/20"
                  : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60"
              )}
            >
              <item.icon size={18} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-gray-800">
        <button
          onClick={logout}
          className="flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium
                     text-gray-500 hover:text-red-400 hover:bg-red-500/10 transition w-full"
        >
          <LogOut size={18} />
          Sign Out
        </button>
      </div>
    </aside>
  );
}