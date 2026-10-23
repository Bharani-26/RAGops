import React, { useEffect, useState } from "react";
import { DollarSign, Cpu, Layers, HelpCircle, AlertCircle } from "lucide-react";
import { api } from "../services/api";
import { MetricsSummary, RequestTrace } from "../types/api";
import { ClearDataButton } from "../components/ClearDataButton";

export const CostAnalyticsPage: React.FC = () => {
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [traces, setTraces] = useState<RequestTrace[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [m, t] = await Promise.all([api.getMetrics(), api.getTraces()]);
        setMetrics(m);
        setTraces(t);
      } catch (err) {
        console.error("Failed to load cost analytics", err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  return (
    <div className="flex-1 p-8 overflow-y-auto space-y-8 bg-[#0b1120]">
      <div className="flex justify-end">
        <ClearDataButton scope="telemetry" onCleared={() => { setMetrics(null); setTraces([]); }} />
      </div>
      {/* Estimation Notice */}
      <div className="p-4 rounded-xl bg-blue-950/30 border border-blue-900/40 flex items-start gap-3 text-xs text-blue-300">
        <HelpCircle className="w-5 h-5 shrink-0 text-blue-400 mt-0.5" />
        <div>
          <span className="font-semibold text-slate-100">Cost Calculation Notice:</span>
          <p className="mt-0.5 text-slate-400">
            All costs presented here are estimated based on token volume, retrieved context size, and official Google Gemini 3.8 Flash model pricing (~$0.00015 per query). Live billing telemetry is fetched from recorded request traces.
          </p>
        </div>
      </div>

      {/* Cost Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div className="p-5 rounded-xl bg-[#0f172a] border border-slate-800 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Total Incurred Cost</span>
            <DollarSign className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-3">
            <h3 className="text-2xl font-bold text-slate-100">
              ${(metrics?.total_cost ?? 0).toFixed(5)}
            </h3>
            <p className="text-[11px] text-slate-400 mt-1">Across {metrics?.total_requests ?? 0} total requests</p>
          </div>
        </div>

        <div className="p-5 rounded-xl bg-[#0f172a] border border-slate-800 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Avg Cost / Request</span>
            <Cpu className="w-4 h-4 text-blue-400" />
          </div>
          <div className="mt-3">
            <h3 className="text-2xl font-bold text-slate-100">
              ${metrics && metrics.total_requests > 0
                ? ((metrics.total_cost ?? 0) / metrics.total_requests).toFixed(6)
                : "0.000000"}
            </h3>
            <p className="text-[11px] text-slate-400 mt-1">Grounded retrieval + generation</p>
          </div>
        </div>

        <div className="p-5 rounded-xl bg-[#0f172a] border border-slate-800 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Primary Model</span>
            <Layers className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="mt-3">
            <h3 className="text-lg font-bold text-slate-100 font-mono">gemini-3.8-flash</h3>
            <p className="text-[11px] text-slate-400 mt-1">Google Generative AI</p>
          </div>
        </div>
      </div>

      {/* Cost By Request Breakdown */}
      <div className="p-6 rounded-xl bg-[#0f172a] border border-slate-800 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-100 mb-4">Request Cost Ledger</h3>

        {traces.length === 0 ? (
          <div className="py-12 text-center border border-dashed border-slate-800 rounded-lg">
            <DollarSign className="w-8 h-8 text-slate-600 mx-auto mb-2" />
            <p className="text-xs text-slate-400">No telemetry traces recorded yet.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-[#121c32] text-slate-400 uppercase text-[10px] tracking-wider">
                <tr>
                  <th className="py-2.5 px-4 rounded-l-lg">Request ID</th>
                  <th className="py-2.5 px-4">Query</th>
                  <th className="py-2.5 px-4">Model</th>
                  <th className="py-2.5 px-4">Latency</th>
                  <th className="py-2.5 px-4 rounded-r-lg text-right">Est. Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80">
                {traces.map((t) => (
                  <tr key={t.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 font-mono text-[11px] text-blue-400">{t.id.slice(0, 8)}...</td>
                    <td className="py-3 px-4 max-w-sm truncate text-slate-200">{t.query}</td>
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-400">{t.model}</td>
                    <td className="py-3 px-4 font-mono">{t.latency_ms} ms</td>
                    <td className="py-3 px-4 font-mono text-right text-emerald-400">
                      {t.estimated_cost == null ? "Unavailable" : `$${t.estimated_cost.toFixed(5)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
