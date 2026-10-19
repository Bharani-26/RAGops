import React, { useState, useEffect } from "react";
import {
  Search,
  Filter,
  Activity,
  Layers,
  Clock,
  DollarSign,
  ChevronRight,
  X,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { api } from "../services/api";
import { RequestTrace } from "../types/api";

export const TracesPage: React.FC = () => {
  const [traces, setTraces] = useState<RequestTrace[]>([]);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [selectedTrace, setSelectedTrace] = useState<RequestTrace | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchTraces = async () => {
      try {
        const data = await api.getTraces();
        setTraces(data);
      } catch (err) {
        console.error("Failed to load traces", err);
      } finally {
        setLoading(false);
      }
    };
    fetchTraces();
  }, []);

  const filteredTraces = traces.filter((t) => {
    const matchesSearch =
      t.query.toLowerCase().includes(search.toLowerCase()) ||
      t.id.toLowerCase().includes(search.toLowerCase()) ||
      t.model.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = filterStatus === "all" || t.status === filterStatus;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="flex-1 flex overflow-hidden bg-[#0b1120]">
      {/* Trace Table List */}
      <div className="flex-1 p-8 overflow-y-auto space-y-6">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="relative w-full sm:w-80">
            <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
            <input
              type="text"
              placeholder="Search by query, ID, or model..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 rounded-lg bg-[#0f172a] border border-slate-800 text-xs text-slate-200 placeholder-slate-400 focus:outline-none focus:border-blue-500"
            />
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <Filter className="w-4 h-4 text-slate-400" />
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="bg-[#0f172a] border border-slate-800 rounded-lg text-xs text-slate-300 px-3 py-2 focus:outline-none focus:border-blue-500"
            >
              <option value="all">All Statuses</option>
              <option value="success">Success Only</option>
              <option value="error">Errors Only</option>
            </select>
          </div>
        </div>

        {filteredTraces.length === 0 ? (
          <div className="py-16 text-center border border-dashed border-slate-800 rounded-xl bg-[#0f172a]/40">
            <Activity className="w-10 h-10 text-slate-600 mx-auto mb-3" />
            <h4 className="text-sm font-semibold text-slate-200">No Request Traces Recorded</h4>
            <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
              Pipeline executions with retrieval latency and stage traces will appear here automatically.
            </p>
          </div>
        ) : (
          <div className="rounded-xl border border-slate-800 bg-[#0f172a] overflow-hidden shadow-sm">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-[#121c32] text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="py-3 px-4">Request ID</th>
                  <th className="py-3 px-4">Query</th>
                  <th className="py-3 px-4">Model</th>
                  <th className="py-3 px-4">Latency</th>
                  <th className="py-3 px-4">Chunks</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80">
                {filteredTraces.map((trace) => (
                  <tr
                    key={trace.id}
                    onClick={() => setSelectedTrace(trace)}
                    className="hover:bg-slate-800/30 cursor-pointer transition-colors"
                  >
                    <td className="py-3 px-4 font-mono text-[11px] text-blue-400">
                      {trace.id.slice(0, 8)}...
                    </td>
                    <td className="py-3 px-4 max-w-xs truncate text-slate-200" title={trace.query}>
                      {trace.query}
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-400">{trace.model}</td>
                    <td className="py-3 px-4 font-mono">{trace.latency_ms} ms</td>
                    <td className="py-3 px-4">{trace.source_count} chunks</td>
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-medium border ${
                          trace.status === "success"
                            ? "bg-emerald-950/60 text-emerald-400 border-emerald-800/50"
                            : "bg-rose-950/60 text-rose-400 border-rose-800/50"
                        }`}
                      >
                        {trace.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right text-slate-400">
                      <ChevronRight className="w-4 h-4 ml-auto" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Slide-out Trace Detail Panel */}
      {selectedTrace && (
        <div className="w-96 border-l border-slate-800 bg-[#0c1424] flex flex-col justify-between shrink-0 shadow-2xl">
          <div className="p-6 overflow-y-auto space-y-6">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h3 className="text-sm font-semibold text-slate-100">Trace Waterfall</h3>
                <p className="text-[10px] font-mono text-slate-400">{selectedTrace.id}</p>
              </div>
              <button
                onClick={() => setSelectedTrace(null)}
                className="text-slate-400 hover:text-slate-200 p-1 rounded hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Overview Stats */}
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-lg bg-[#0f172a] border border-slate-800">
                <span className="text-slate-400 text-[10px] uppercase">Total Latency</span>
                <p className="text-sm font-semibold text-slate-200 mt-0.5">{selectedTrace.latency_ms} ms</p>
              </div>
              <div className="p-3 rounded-lg bg-[#0f172a] border border-slate-800">
                <span className="text-slate-400 text-[10px] uppercase">Est. Cost</span>
                <p className="text-sm font-semibold text-slate-200 mt-0.5">
                  {selectedTrace.estimated_cost == null ? "Unavailable" : `$${selectedTrace.estimated_cost.toFixed(5)}`}
                </p>
              </div>
            </div>

            {/* Stages Waterfall */}
            <div>
              <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-3">
                Execution Pipeline Stages
              </h4>
              <div className="space-y-3">
                {selectedTrace.stages && selectedTrace.stages.length > 0 ? (
                  selectedTrace.stages.map((stage, idx) => (
                    <div
                      key={idx}
                      className="p-3 rounded-lg bg-[#0f172a] border border-slate-800/80 space-y-1.5"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium text-slate-200 flex items-center gap-1.5">
                          {stage.status === "success" ? (
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
                          )}
                          {stage.name}
                        </span>
                        {stage.duration_ms !== undefined && (
                          <span className="font-mono text-[11px] text-blue-400">
                            {stage.duration_ms} ms
                          </span>
                        )}
                      </div>
                      {stage.details && <p className="text-[11px] text-slate-400">{stage.details}</p>}
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-slate-400">No individual sub-stages recorded for this request.</p>
                )}
              </div>
            </div>

            {/* Generated Answer */}
            {selectedTrace.answer && (
              <div>
                <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">Answer Generated</h4>
                <div className="p-3 rounded-lg bg-[#0a101d] border border-slate-800 text-xs text-slate-300 leading-relaxed max-h-40 overflow-y-auto">
                  {selectedTrace.answer}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
