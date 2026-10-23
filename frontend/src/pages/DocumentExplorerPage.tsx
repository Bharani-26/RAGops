import React, { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, FileSearch, RefreshCw, Search } from "lucide-react";
import { api } from "../services/api";
import { ChunkDocumentSummary, StoredChunk } from "../types/api";

const PAGE_SIZE = 10;

export const DocumentExplorerPage: React.FC = () => {
  const [chunks, setChunks] = useState<StoredChunk[]>([]);
  const [documents, setDocuments] = useState<ChunkDocumentSummary[]>([]);
  const [search, setSearch] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadChunks = async (requestedPage = page, filter = activeSearch) => {
    setLoading(true);
    setError(null);
    try {
      const isDocumentId = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(filter);
      const response = await api.listChunks({
        page: requestedPage,
        pageSize: PAGE_SIZE,
        documentId: isDocumentId ? filter : undefined,
        filename: isDocumentId ? undefined : filter || undefined,
      });
      setChunks(response.chunks);
      setDocuments(response.documents);
      setPage(response.page);
      setTotal(response.total);
      setTotalPages(response.total_pages);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load stored chunks.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadChunks(1, "");
  }, []);

  const submitSearch = (event: React.FormEvent) => {
    event.preventDefault();
    setActiveSearch(search.trim());
    void loadChunks(1, search.trim());
  };

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">Stored document chunks</h2>
            <p className="mt-1 text-sm text-slate-400">Live records from the existing ChromaDB collection.</p>
          </div>
          <button onClick={() => void loadChunks()} className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800">
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
        </div>

        <form onSubmit={submitSearch} className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Filter by filename or document ID" className="w-full rounded-lg border border-slate-700 bg-[#11192e] py-2.5 pl-9 pr-3 text-sm text-slate-200 outline-none focus:border-blue-500" />
          </div>
          <button type="submit" className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500">Search</button>
        </form>

        {documents.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {documents.map((document) => (
              <div key={document.document_id} className="rounded-lg border border-slate-800 bg-[#11192e] p-4">
                <div className="flex items-start gap-2">
                  <FileSearch className="mt-0.5 h-4 w-4 shrink-0 text-blue-400" />
                  <div className="min-w-0">
                    <p className="truncate text-sm text-slate-200" title={document.filename}>{document.filename}</p>
                    <p className="mt-1 text-xs text-slate-500">{document.chunk_count} chunks</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {error && <div className="rounded-lg border border-rose-900/60 bg-rose-950/30 p-4 text-sm text-rose-300">{error}</div>}
        {loading ? (
          <div className="rounded-lg border border-slate-800 bg-[#11192e] p-12 text-center text-sm text-slate-400">Loading stored chunks...</div>
        ) : chunks.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-700 p-12 text-center text-sm text-slate-400">{activeSearch ? "No chunks match this filter." : "No documents have been indexed yet."}</div>
        ) : (
          <div className="space-y-3">
            {chunks.map((chunk) => (
              <article key={chunk.chunk_id} className="rounded-lg border border-slate-800 bg-[#11192e] p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-slate-200">{chunk.filename}</p>
                    <p className="mt-1 text-[11px] text-slate-500">Chunk {String(chunk.metadata.chunk_index ?? "—")} · {chunk.page_number ? `Page ${chunk.page_number} · ` : ""}{chunk.document_id}</p>
                  </div>
                  <span className="rounded bg-slate-800 px-2 py-1 font-mono text-[10px] text-slate-400">{chunk.chunk_id}</span>
                </div>
                <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-slate-300">{chunk.text}</p>
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs text-blue-400">Metadata</summary>
                  <pre className="mt-2 overflow-x-auto rounded bg-[#0a0f1d] p-3 text-[11px] text-slate-400">{JSON.stringify(chunk.metadata, null, 2)}</pre>
                </details>
              </article>
            ))}
          </div>
        )}

        {!loading && total > 0 && (
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>{total} chunks · Page {page} of {totalPages}</span>
            <div className="flex gap-2">
              <button disabled={page <= 1} onClick={() => void loadChunks(page - 1)} className="rounded border border-slate-700 p-2 disabled:cursor-not-allowed disabled:opacity-40"><ChevronLeft className="h-4 w-4" /></button>
              <button disabled={page >= totalPages} onClick={() => void loadChunks(page + 1)} className="rounded border border-slate-700 p-2 disabled:cursor-not-allowed disabled:opacity-40"><ChevronRight className="h-4 w-4" /></button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
