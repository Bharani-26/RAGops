import React, { useEffect, useState } from "react";
import { CheckCircle2, Play, RefreshCw, ShieldCheck, Target, XCircle } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../services/api";
import { EvaluationCorpusStatus, EvaluationDataset, EvaluationRun, EvaluationRunDetail } from "../types/api";
import { ClearDataButton } from "../components/ClearDataButton";

const score = (value: number | null | undefined) => value == null ? "Unavailable" : value.toFixed(2);

export const EvaluationsPage: React.FC = () => {
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([]);
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [selectedDataset, setSelectedDataset] = useState("");
  const [detail, setDetail] = useState<EvaluationRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [corpus, setCorpus] = useState<EvaluationCorpusStatus | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextDatasets, nextRuns, nextCorpus] = await Promise.all([
        api.getEvaluationDatasets(),
        api.getEvaluationRuns(),
        api.getEvaluationCorpus(),
      ]);
      setDatasets(nextDatasets);
      setRuns(nextRuns);
      setCorpus(nextCorpus);
      if (!selectedDataset && nextDatasets.length) {
        setSelectedDataset(`${nextDatasets[0].dataset_id}:${nextDatasets[0].version}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load evaluations");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const runSelected = async () => {
    if (!selectedDataset) return;
    const [datasetId, version] = selectedDataset.split(":");
    setRunning(true);
    setError(null);
    try {
      const result = await api.runEvaluation(datasetId, version);
      setDetail(result);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation run failed");
    } finally {
      setRunning(false);
    }
  };

  const openRun = async (runId: string) => {
    try {
      setDetail(await api.getEvaluationRun(runId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load run details");
    }
  };

  const activeDataset = datasets.find((dataset) => `${dataset.dataset_id}:${dataset.version}` === selectedDataset);
  const corpusReady = Boolean(corpus && corpus.chunk_count > 0);

  return (
    <div className="flex-1 space-y-6 overflow-y-auto bg-[#0b1120] p-8">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-[#353d48] bg-[#252b35] p-6">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-blue-400">RAG quality evaluation</p>
          <h2 className="mt-1 flex items-center gap-2 text-base font-semibold text-slate-100"><ShieldCheck className="h-5 w-5 text-blue-400" /> Evaluation engine</h2>
          <p className="mt-1 max-w-2xl text-xs text-slate-400">Runs actual retrieval and Gemini generation against versioned test cases. Scores are deterministic development metrics, not scientific validation claims.</p>
        </div>
        <div className="flex items-center gap-2">
          <ClearDataButton scope="evaluations" onCleared={() => { setRuns([]); setDetail(null); }} />
          <select value={selectedDataset} onChange={(event) => setSelectedDataset(event.target.value)} className="rounded-lg border border-slate-700 bg-[#0f172a] px-3 py-2 text-xs text-slate-300">
            <option value="">Select dataset</option>
            {datasets.map((dataset) => <option key={`${dataset.dataset_id}:${dataset.version}`} value={`${dataset.dataset_id}:${dataset.version}`}>{dataset.name} · v{dataset.version}</option>)}
          </select>
          <button onClick={() => void runSelected()} disabled={!selectedDataset || running || !corpusReady} className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-50">
            {running ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />} Run evaluation
          </button>
        </div>
      </div>

      {error && <div className="rounded-lg border border-rose-900/60 bg-rose-950/30 p-4 text-sm text-rose-300">{error}</div>}
      {activeDataset?.sample && <div className="rounded-lg border border-amber-900/50 bg-amber-950/20 p-3 text-xs text-amber-300">Sample dataset: development-only cases. Results must not be treated as production evaluation results.</div>}
      {corpus && <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-xs text-slate-400">
        Evaluation corpus <span className="text-slate-200">{corpus.corpus_version}</span> · isolated collection <span className="text-slate-200">{corpus.collection}</span> · {corpus.document_count} documents · {corpus.chunk_count} indexed chunks
      </div>}
      {corpus && corpus.chunk_count === 0 && (
        <div className="rounded-lg border border-amber-900/50 bg-amber-950/20 p-4 text-xs text-amber-300">
          The evaluation corpus has no indexed chunks. Run <code className="font-mono text-amber-200">python -m backend.prepare_eval_corpus</code> from the project root, then refresh this page before starting an evaluation.
        </div>
      )}

      {detail && (
        <>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-4">
            <Metric label="Retrieval relevance" value={detail.avg_relevance} icon={<Target className="h-4 w-4 text-blue-400" />} />
            <Metric label="Faithfulness" value={detail.avg_faithfulness} icon={<ShieldCheck className="h-4 w-4 text-emerald-400" />} />
            <Metric label="Answer correctness" value={detail.avg_correctness} icon={<CheckCircle2 className="h-4 w-4 text-indigo-400" />} />
            <Metric label="Citation accuracy" value={detail.avg_citation_precision} icon={<Target className="h-4 w-4 text-amber-400" />} />
          </div>
          <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-5 text-xs text-slate-400">
            Run status: <span className="text-slate-200">{detail.status}</span> · {detail.completed_samples} generated · {detail.failed_samples} failed · threshold status: <span className="text-slate-200">{detail.threshold_status || "not_configured"}</span> · dataset v{detail.dataset_version} · corpus v{detail.corpus_version || "unknown"} · {detail.timestamp ? new Date(detail.timestamp * 1000).toLocaleString() : "timestamp unavailable"}
            {detail.threshold_failures && detail.threshold_failures.length > 0 && <p className="mt-2 text-rose-300">{detail.threshold_failures.join(" · ")}</p>}
            <p className="mt-2">Available metrics: {Object.entries(detail.metric_availability || {}).filter(([, available]) => available).map(([metric]) => metric).join(", ") || "none"} · Retrieval p50: {detail.retrieval_latency_p50_ms == null ? "Unavailable" : `${detail.retrieval_latency_p50_ms} ms`} · Generation p50: {detail.generation_latency_p50_ms == null ? "Unavailable" : `${detail.generation_latency_p50_ms} ms`}</p>
          </div>
          <div className="overflow-hidden rounded-xl border border-slate-800 bg-[#0f172a]">
            <div className="border-b border-slate-800 p-5"><h3 className="text-sm font-semibold text-slate-100">Question-level results</h3></div>
            <div className="divide-y divide-slate-800/80">{detail.results.map((result) => <div key={result.id} className="p-5">
              <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm text-slate-200">{result.question}</p>{result.status === "completed" ? <span className="text-xs text-emerald-400">Generated</span> : result.status === "retrieval_only" ? <span className="text-xs text-blue-400">Retrieval only</span> : <span className="flex items-center gap-1 text-xs text-rose-400"><XCircle className="h-3.5 w-3.5" /> {result.error_type}</span>}</div>
              {result.status === "completed" || result.status === "retrieval_only" ? <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-slate-400 md:grid-cols-4"><span>Relevance <b className="text-slate-200">{score(result.relevance_score)}</b></span><span>Faithfulness <b className="text-slate-200">{score(result.faithfulness_score)}</b></span><span>Correctness <b className="text-slate-200">{score(result.correctness_score)}</b></span><span>Citations <b className="text-slate-200">{score(result.citation_score)}</b></span></div> : <p className="mt-2 text-xs text-rose-300">{result.error_message}</p>}
              <details className="mt-3 text-xs text-slate-400"><summary className="cursor-pointer text-blue-400">View evidence and metric limitations</summary><div className="mt-3 space-y-2"><p><b>Expected:</b> {result.ground_truth}</p><p><b>Generated:</b> {result.generated_answer || "Unavailable"}</p><p><b>Retrieved chunks:</b> {result.retrieved_chunks.length}</p>{result.unsupported_claims.length > 0 && <p className="text-amber-300"><b>Unsupported claims:</b> {result.unsupported_claims.join(" | ")}</p>}</div></details>
            </div>)}</div>
          </div>
        </>
      )}

      {runs.length > 1 && (
        <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-5">
          <h3 className="text-sm font-semibold text-slate-100">Metric trends across completed runs</h3>
          <p className="mb-4 mt-1 text-xs text-slate-400">Only persisted aggregate scores are plotted; unavailable values are omitted.</p>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={[...runs].reverse().map((run, index) => ({
                run: index + 1,
                relevance: run.retrieval_relevance,
                faithfulness: run.faithfulness,
                correctness: run.answer_correctness,
                citations: run.citation_accuracy,
              }))}>
                <CartesianGrid stroke="#353d48" strokeDasharray="3 3" />
                <XAxis dataKey="run" stroke="#9aa5b1" fontSize={11} />
                <YAxis domain={[0, 1]} stroke="#9aa5b1" fontSize={11} />
                <Tooltip contentStyle={{ backgroundColor: "#0b1220", borderColor: "#334155", color: "#f8fafc", fontSize: "12px" }} />
                <Line type="monotone" dataKey="relevance" stroke="#5bb7aa" name="Relevance" connectNulls />
                <Line type="monotone" dataKey="faithfulness" stroke="#34d399" name="Faithfulness" connectNulls />
                <Line type="monotone" dataKey="correctness" stroke="#818cf8" name="Correctness" connectNulls />
                <Line type="monotone" dataKey="citations" stroke="#fbbf24" name="Citations" connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-5">
        <div className="mb-4 flex items-center justify-between"><div><h3 className="text-sm font-semibold text-slate-100">Evaluation run history</h3><p className="mt-1 text-xs text-slate-400">Persisted SQLite results</p></div><button onClick={() => void load()} className="text-slate-400 hover:text-white"><RefreshCw className="h-4 w-4" /></button></div>
        {loading ? <p className="py-8 text-center text-xs text-slate-400">Loading evaluation data...</p> : runs.length === 0 ? <p className="rounded-lg border border-dashed border-slate-700 py-12 text-center text-xs text-slate-400">No evaluation runs yet.</p> : <div className="space-y-2">{runs.map((run) => { const runId = run.run_id || run.id; return <button key={runId} onClick={() => void openRun(runId)} className="flex w-full items-center justify-between rounded-lg border border-slate-800 bg-[#121c32] p-3 text-left hover:border-blue-800"><span><span className="block text-xs text-slate-200">{run.dataset_name} · v{run.dataset_version}</span><span className="text-[11px] text-slate-500">{run.total_samples} cases · {run.status}</span></span><span className="text-xs text-blue-400">View</span></button>; })}</div>}
      </div>
    </div>
  );
};

const Metric: React.FC<{ label: string; value: number | null | undefined; icon: React.ReactNode }> = ({ label, value, icon }) => (
  <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-5"><div className="flex items-center justify-between"><span className="text-xs uppercase tracking-wider text-slate-400">{label}</span>{icon}</div><p className="mt-3 text-2xl font-bold text-slate-100">{score(value)}</p><p className="mt-1 text-[11px] text-slate-500">0–1 deterministic score</p></div>
);
