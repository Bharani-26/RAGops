import React, { useEffect, useState } from "react";
import { Settings, Shield, Server, Key, Database, Cpu, CheckCircle2, AlertTriangle } from "lucide-react";
import { api } from "../services/api";
import { AppSettings } from "../types/api";
import { ClearDataButton } from "../components/ClearDataButton";

export const SettingsPage: React.FC = () => {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const data = await api.getSettings();
        setSettings(data);
      } catch (err) {
        console.error("Failed to load settings", err);
      } finally {
        setLoading(false);
      }
    };
    fetchSettings();
  }, []);

  return (
    <div className="flex-1 p-8 overflow-y-auto space-y-8 bg-[#0b1120]">
      <div className="flex justify-end">
        <ClearDataButton scope="all" label="Clear all runtime data" />
      </div>
      {/* Security Banner */}
      <div className="p-4 rounded-xl bg-[#0f172a] border border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-blue-950 border border-blue-800/40 flex items-center justify-center text-blue-400">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-100">Zero-Secret Exposure Architecture</h3>
            <p className="text-xs text-slate-400">
              API keys and vector secrets remain secured server-side in .env and are never passed to the client browser.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {settings?.api_key_configured ? (
            <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-950/60 border border-emerald-800/50 text-emerald-400 text-xs font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              GOOGLE_API_KEY Configured
            </span>
          ) : (
            <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-rose-950/60 border border-rose-800/50 text-rose-400 text-xs font-medium">
              <AlertTriangle className="w-3.5 h-3.5" />
              API Key Not Configured
            </span>
          )}
        </div>
      </div>

      {/* Configuration Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Model Configurations */}
        <div className="p-6 rounded-xl bg-[#0f172a] border border-slate-800 space-y-4">
          <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
            <Cpu className="w-4 h-4 text-blue-400" />
            Active AI Models
          </h3>

          <div className="space-y-3 text-xs">
            <div className="p-3 rounded-lg bg-[#0a101d] border border-slate-800 flex items-center justify-between">
              <div>
                <p className="text-slate-400 font-medium">Generation Model</p>
                <p className="text-slate-200 font-mono text-[11px] mt-0.5">{settings?.llm_model ?? "Loading..."}</p>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800/50">
                Primary LLM
              </span>
            </div>

            <div className="p-3 rounded-lg bg-[#0a101d] border border-slate-800 flex items-center justify-between">
              <div>
                <p className="text-slate-400 font-medium">Embedding Model</p>
                <p className="text-slate-200 font-mono text-[11px] mt-0.5">{settings?.embedding_model ?? "Loading..."}</p>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-950 text-indigo-400 border border-indigo-800/50">
                3072 dims
              </span>
            </div>

            <div className="p-3 rounded-lg bg-[#0a101d] border border-slate-800 flex items-center justify-between">
              <div>
                <p className="text-slate-400 font-medium">Model Temperature</p>
                <p className="text-slate-200 font-mono text-[11px] mt-0.5">{settings?.temperature ?? 0.0}</p>
              </div>
              <span className="text-slate-400 text-[11px]">Strict Factuality</span>
            </div>
          </div>
        </div>

        {/* Vector DB & Chunking Settings */}
        <div className="p-6 rounded-xl bg-[#0f172a] border border-slate-800 space-y-4">
          <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
            <Database className="w-4 h-4 text-indigo-400" />
            Retrieval & Storage
          </h3>

          <div className="space-y-3 text-xs">
            <div className="p-3 rounded-lg bg-[#0a101d] border border-slate-800 flex items-center justify-between">
              <div>
                <p className="text-slate-400 font-medium">Chroma Collection</p>
                <p className="text-slate-200 font-mono text-[11px] mt-0.5">{settings?.chroma_collection ?? "Loading..."}</p>
              </div>
              <span className="text-emerald-400 text-[11px]">Persistent SQLite</span>
            </div>

            <div className="p-3 rounded-lg bg-[#0a101d] border border-slate-800 flex items-center justify-between">
              <div>
                <p className="text-slate-400 font-medium">Chunk Configuration</p>
                <p className="text-slate-200 font-mono text-[11px] mt-0.5">
                  Size: {settings?.default_chunk_size ?? 500} chars • Overlap: {settings?.default_chunk_overlap ?? 50} chars
                </p>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-[#0a101d] border border-slate-800 flex items-center justify-between">
              <div>
                <p className="text-slate-400 font-medium">Default Top-K Retrieved</p>
                <p className="text-slate-200 font-mono text-[11px] mt-0.5">{settings?.default_top_k ?? 4} chunks</p>
              </div>
              <span className="text-blue-400 text-[11px]">Cosine Distance</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
