import React, { useCallback, useEffect, useState } from "react";
import {
  Activity, Clock, DollarSign, RefreshCw, Server,
} from "lucide-react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../services/api";
import {
  CostMetrics, ErrorMetrics, LatencyMetrics, ObservabilityOverview,
  ObservabilityRequest,
} from "../types/api";

const chartTooltip = {
  backgroundColor: "#0b1220",
  borderColor: "#334155",
  color: "#f8fafc",
  borderRadius: "8px",
  fontSize: "12px",
};

const formatParam = (range: string, status: string) => {
  const params = new URLSearchParams();
  if (range !== "all") {
    const start = new Date();
    start.setDate(start.getDate() - Number(range));
    params.set("date_from", start.toISOString());
  }
  if (status !== "all") params.set("status", status);
  const query = params.toString();
  return query ? `?${query}` : "";
};

const Card: React.FC<{ label: string; value: string; note: string; icon: React.ReactNode }> = ({
  label, value, note, icon,
}) => (
  <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-5 shadow-sm">
    <div className="flex items-center justify-between">
      <span className="text-xs font-medium uppercase tracking-wider text-slate-400">{label}</span>
      <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-blue-800/40 bg-blue-950 text-blue-400">{icon}</div>
    </div>
    <p className="mt-3 text-2xl font-bold text-slate-100">{value}</p>
    <p className="mt-1 text-[11px] text-slate-400">{note}</p>
  </div>
);

export const DashboardPage: React.FC = () => {
  const [overview, setOverview] = useState<ObservabilityOverview | null>(null);
  const [requests, setRequests] = useState<ObservabilityRequest[]>([]);
  const [latency, setLatency] = useState<LatencyMetrics | null>(null);
  const [errors, setErrors] = useState<ErrorMetrics | null>(null);
  const [costs, setCosts] = useState<CostMetrics | null>(null);
  const [range, setRange] = useState("all");
  const [status, setStatus] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = formatParam(range, status);
      const [nextOverview, nextRequests, nextLatency, nextErrors, nextCosts] = await Promise.all([
        api.getObservabilityOverview(params),
        api.getObservabilityRequests(`${params}${params ? "&" : "?"}page_size=10`),
        api.getLatencyMetrics(params),
        api.getErrorMetrics(params),
        api.getCostMetrics(params),
      ]);
      setOverview(nextOverview);
      setRequests(nextRequests.requests);
      setLatency(nextLatency);
      setErrors(nextErrors);
      setCosts(nextCosts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard metrics");
    } finally {
      setLoading(false);
    }
  }, [range, status]);

  useEffect(() => { void load(); }, [load]);

  const noData = !loading && !error && !overview?.total_requests;
  const latencyData = (latency?.points || []).map((point) => ({
    time: new Date(point.timestamp * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    latency: Math.round(point.latency_ms),
  }));
  const errorData = errors?.errors.map((item) => ({ name: item.error_type, count: item.count })) || [];
  const costData = costs?.points.map((point) => ({
    time: new Date(point.timestamp * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    input: point.input_tokens || 0,
    output: point.output_tokens || 0,
  })) || [];

  return (
    <div className="flex-1 space-y-6 overflow-y-auto bg-[#0b1120] p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-blue-400">Live telemetry</p>
          <h2 className="mt-1 text-xl font-semibold text-slate-100">Pipeline performance overview</h2>
        </div>
        <div className="flex items-center gap-2">
          <select value={range} onChange={(event) => setRange(event.target.value)} className="rounded-lg border border-slate-800 bg-[#0f172a] px-3 py-2 text-xs text-slate-300">
            <option value="all">All time</option><option value="1">Last 24 hours</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option>
          </select>
          <select value={status} onChange={(event) => setStatus(event.target.value)} className="rounded-lg border border-slate-800 bg-[#0f172a] px-3 py-2 text-xs text-slate-300">
            <option value="all">All statuses</option><option value="success">Success</option><option value="error">Errors</option>
          </select>
          <button onClick={() => void load()} className="flex items-center gap-2 rounded-lg border border-blue-800/50 bg-blue-950/50 px-3 py-2 text-xs text-blue-300 hover:bg-blue-900/50">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
          </button>
        </div>
      </div>

      {error && <div className="rounded-lg border border-rose-900/60 bg-rose-950/30 p-4 text-sm text-rose-300">{error}</div>}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
        <Card label="Total requests" value={loading ? "—" : String(overview?.total_requests ?? 0)} note={`${overview?.failure_count ?? 0} failed requests`} icon={<Activity className="h-4 w-4" />} />
        <Card label="Success rate" value={loading ? "—" : `${overview?.success_rate ?? 0}%`} note={`${overview?.success_count ?? 0} successful requests`} icon={<Server className="h-4 w-4" />} />
        <Card label="p95 latency" value={overview?.p95_latency_ms == null ? "Unavailable" : `${overview.p95_latency_ms} ms`} note={`p50: ${overview?.p50_latency_ms == null ? "Unavailable" : `${overview.p50_latency_ms} ms`}`} icon={<Clock className="h-4 w-4" />} />
        <Card label="Estimated cost" value={overview?.cost_available ? `$${overview.estimated_cost?.toFixed(6)}` : "Unavailable"} note={overview?.cost_available ? "From recorded token usage" : "Pricing or usage is unavailable"} icon={<DollarSign className="h-4 w-4" />} />
      </div>

      {noData ? (
        <div className="rounded-xl border border-dashed border-slate-700 bg-[#0f172a]/60 py-20 text-center">
          <Activity className="mx-auto mb-3 h-10 w-10 text-slate-600" />
          <h3 className="text-sm font-semibold text-slate-200">No persisted request telemetry yet</h3>
          <p className="mt-1 text-xs text-slate-400">Run a document question to populate this dashboard with real measurements.</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <ChartPanel title="Latency trend" subtitle="Successful requests only">
              {latencyData.length ? <ResponsiveContainer width="100%" height="100%"><AreaChart data={latencyData}><defs><linearGradient id="latencyFill" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#3b82f6" stopOpacity={0.45} /><stop offset="95%" stopColor="#3b82f6" stopOpacity={0} /></linearGradient></defs><CartesianGrid stroke="#1e293b" strokeDasharray="3 3" /><XAxis dataKey="time" stroke="#64748b" fontSize={11} /><YAxis stroke="#64748b" fontSize={11} /><Tooltip contentStyle={chartTooltip} /><Area dataKey="latency" stroke="#60a5fa" fill="url(#latencyFill)" /></AreaChart></ResponsiveContainer> : <EmptyChart text="No successful latency points in this range." />}
            </ChartPanel>
            <ChartPanel title="Error distribution" subtitle="Persisted failure types">
              {errorData.length ? <ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={errorData} dataKey="count" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={3}>{errorData.map((entry, index) => <Cell key={entry.name} fill={["#f43f5e", "#f59e0b", "#8b5cf6", "#06b6d4"][index % 4]} />)}</Pie><Tooltip contentStyle={chartTooltip} /></PieChart></ResponsiveContainer> : <EmptyChart text="No errors recorded in this range." />}
            </ChartPanel>
          </div>
          <ChartPanel title="Token usage" subtitle={overview?.token_usage_available ? "Reported by Gemini response metadata" : "Token usage unavailable; no values are invented"}>
            {costData.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={costData}><CartesianGrid stroke="#1e293b" strokeDasharray="3 3" /><XAxis dataKey="time" stroke="#64748b" fontSize={11} /><YAxis stroke="#64748b" fontSize={11} /><Tooltip contentStyle={chartTooltip} /><Bar dataKey="input" fill="#3b82f6" name="Input tokens" /><Bar dataKey="output" fill="#8b5cf6" name="Output tokens" /></BarChart></ResponsiveContainer> : <EmptyChart text="Token usage is unavailable for these requests." />}
          </ChartPanel>
          <div className="overflow-hidden rounded-xl border border-slate-800 bg-[#0f172a]">
            <div className="border-b border-slate-800 p-5"><h3 className="text-sm font-semibold text-slate-100">Recent request traces</h3><p className="mt-1 text-xs text-slate-400">Actual persisted RAG executions</p></div>
            {requests.length ? <div className="overflow-x-auto"><table className="w-full text-left text-xs text-slate-300"><thead className="bg-[#121c32] text-[10px] uppercase tracking-wider text-slate-400"><tr><th className="px-5 py-3">Request</th><th className="px-5 py-3">Question</th><th className="px-5 py-3">Chunks</th><th className="px-5 py-3">Latency</th><th className="px-5 py-3">Status</th></tr></thead><tbody className="divide-y divide-slate-800/80">{requests.map((request) => <tr key={request.request_id}><td className="px-5 py-3 font-mono text-blue-400">{request.request_id.slice(0, 8)}...</td><td className="max-w-sm truncate px-5 py-3 text-slate-200">{request.query}</td><td className="px-5 py-3">{request.retrieved_chunks}</td><td className="px-5 py-3">{request.latency_ms} ms</td><td className="px-5 py-3"><span className={request.status === "success" ? "text-emerald-400" : "text-rose-400"}>{request.status}</span></td></tr>)}</tbody></table></div> : <p className="p-8 text-center text-xs text-slate-400">No requests match the selected filters.</p>}
          </div>
        </>
      )}
    </div>
  );
};

const ChartPanel: React.FC<{ title: string; subtitle: string; children: React.ReactNode }> = ({ title, subtitle, children }) => (
  <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-5">
    <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
    <p className="mb-4 mt-1 text-xs text-slate-400">{subtitle}</p>
    <div className="h-60 w-full">{children}</div>
  </div>
);

const EmptyChart: React.FC<{ text: string }> = ({ text }) => (
  <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-slate-800 text-xs text-slate-500">{text}</div>
);
