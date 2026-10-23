import React from "react";
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  MessageSquareText,
  Activity,
  CheckCircle2,
  DollarSign,
  Settings,
  Layers,
  Sparkles,
  FileSearch,
} from "lucide-react";

interface SidebarProps {
  apiStatus: "online" | "offline" | "checking";
}

export const Sidebar: React.FC<SidebarProps> = ({ apiStatus }) => {
  const navItems = [
    { name: "Dashboard", path: "/", icon: LayoutDashboard },
    { name: "Document Chat", path: "/chat", icon: MessageSquareText },
    { name: "Document Explorer", path: "/documents", icon: FileSearch },
    { name: "Request Traces", path: "/traces", icon: Activity },
    { name: "Evaluations", path: "/evaluations", icon: CheckCircle2 },
    { name: "Cost Analytics", path: "/costs", icon: DollarSign },
    { name: "Settings", path: "/settings", icon: Settings },
  ];

  return (
    <aside className="w-64 bg-[#0c1322] border-r border-slate-800/80 flex flex-col justify-between shrink-0 select-none">
      <div>
        {/* Brand / Logo */}
        <div className="h-16 px-6 flex items-center gap-3 border-b border-slate-800/80">
          <div className="w-9 h-9 rounded-lg bg-[#2f8f83] flex items-center justify-center shadow-lg shadow-teal-900/20 text-white font-bold text-lg">
            <Layers className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-100 tracking-wide text-base">RAGOps</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#2f8f83]/20 text-[#8bd1c7] font-medium border border-[#2f8f83]/50">
                v0.2
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-normal">AI Observability & Eval</p>
          </div>
        </div>

        {/* Navigation links */}
        <nav className="p-3 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? "bg-[#2f8f83]/15 text-[#8bd1c7] border border-[#2f8f83]/40 shadow-sm"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
                  }`
                }
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span>{item.name}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* Backend Status footer pill */}
      <div className="p-4 border-t border-slate-800/80">
        <div className="bg-[#11192e] p-3 rounded-lg border border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              {apiStatus === "online" && (
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              )}
              <span
                className={`relative inline-flex rounded-full h-2 w-2 ${
                  apiStatus === "online"
                    ? "bg-emerald-500"
                    : apiStatus === "checking"
                    ? "bg-amber-500"
                    : "bg-rose-500"
                }`}
              ></span>
            </span>
            <span className="text-xs text-slate-300 font-medium">
              API {apiStatus === "online" ? "Online" : apiStatus === "checking" ? "Checking..." : "Offline"}
            </span>
          </div>
          <span className="text-[11px] text-slate-400 font-mono">:8000</span>
        </div>
      </div>
    </aside>
  );
};
