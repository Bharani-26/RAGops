import React from "react";
import { Bell, Sparkles } from "lucide-react";

interface HeaderProps {
  title: string;
  subtitle?: string;
}

export const Header: React.FC<HeaderProps> = ({ title, subtitle }) => {
  return (
    <header className="h-16 px-8 border-b border-slate-800/80 bg-[#0c1322]/60 backdrop-blur-md flex items-center justify-between sticky top-0 z-10">
      <div>
        <h1 className="text-lg font-semibold text-slate-100 tracking-tight">{title}</h1>
        {subtitle && <p className="text-xs text-slate-400">{subtitle}</p>}
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 bg-blue-950/40 border border-blue-800/40 px-3 py-1.5 rounded-full text-xs text-blue-300 font-medium">
          <Sparkles className="w-3.5 h-3.5 text-blue-400" />
          <span>Gemini 3.8 Flash • ChromaDB</span>
        </div>
      </div>
    </header>
  );
};

