# RAGOps — AI Observability & Evaluation Platform for RAG Applications

RAGOps provides continuous observability, monitoring, telemetry tracing, and automated evaluation for Retrieval-Augmented Generation (RAG) pipelines.

## Prerequisites

- Python 3.10 or newer within the tested CI range
- Node.js 20.19.0 or newer (the CI workflow uses 20.19.0)
- npm
- A Google Gemini API key for document embedding and grounded answer generation

The ordinary test and CI paths do not call Gemini. They use mocked provider calls
and isolated local storage. The live demo workflow below requires a valid key.

---

## Persistent Local Storage Architecture

RAGOps uses a purely local, zero-cloud-database storage architecture without Supabase or PostgreSQL:

```
ragops/data/
├── uploads/               # Original uploaded PDF and TXT files with sanitized names
├── chroma/                # Persistent ChromaDB vector database (SQLite + binary vector indices)
└── ragops.db              # SQLite database (managed via SQLAlchemy) for observability & evaluations
```

### Storage Components

1. **Vector Database (ChromaDB)**:
   - **Path**: `data/chroma/`
   - **Collection**: `ragops_documents`
   - **Metadata Stored**: Document ID (`doc_id`), Chunk ID (`chunk_id`), filename/source, page number (`page_number`), chunk index (`chunk_index`), total chunk count (`total_chunks`), character length (`chunk_char_length`), and sanitized server filename.
   - **Persistence**: Reuses persistent collection on startup. Vectors and indices survive application restarts without re-embedding.

2. **Original Documents**:
   - **Path**: `data/uploads/`
   - **Security**: Validates file extensions (`.txt`, `.pdf`) and sizes (max 25 MB). Sanitizes filenames to prevent path traversal and executable exploits.

3. **Observability Database (SQLite + SQLAlchemy)**:
   - **Path**: `data/ragops.db`
   - **Tables**:
     - `request_traces`: Request ID, query, grounded answer, model, latency (ms), status, top-k, source count, sources JSON, execution stages JSON, token estimates, and cost.
     - `evaluation_runs`: Benchmark run ID, dataset name, sample count, triad scores (relevance, faithfulness, answer correctness, citation precision).
     - `evaluation_results`: Per-question ground truth, generated output, context, and metric scores.

4. **Readiness Probe**:
   - `GET /api/rag/ready`: Checks ChromaDB and SQLite accessibility and returns health status.
   - `GET /api/health`: Liveness check for the API process.
   - `GET /api/health/ready`: Readiness check for ChromaDB and SQLite.

### Canonical API endpoints

The frontend-compatible `/api/rag/upload`, `/api/rag/documents`, and
`/api/rag/query` routes remain available. New clients may use:

- `POST /api/documents/upload`
- `GET /api/documents`
- `GET /api/documents/{document_id}`
- `POST /api/rag/query`
- `GET /api/rag/chunks?page=1&page_size=20&filename=report`

The chunk explorer endpoint reads the existing `ragops_documents` collection and
returns persisted chunk text, document ID, filename, page number when available,
metadata, pagination, and document chunk counts. It does not create a second
database or collection.

Document listings and details are read from persisted Chroma metadata rather
than from a hardcoded sample list. Uploads are content-hash idempotent, so
re-uploading the same bytes reuses the existing document and chunks.

---

## Project Structure

```
ragops/
├── backend/
│   ├── __init__.py          # Package initialization
│   ├── config.py            # Central configuration (Pydantic Settings + .env)
│   ├── database.py          # SQLAlchemy SQLite models, engine & queries
│   ├── ingestion.py         # File validation, page extraction (PDF/TXT), and chunking
│   ├── retrieval.py         # Gemini embeddings & persistent ChromaDB store
│   ├── generation.py        # Strict grounded Q&A with Gemini LLM
│   ├── routes.py            # API routes (upload, query, documents, traces, metrics, ready)
│   ├── main.py              # FastAPI application root & health endpoints
│   └── requirements.txt     # Python dependencies
├── frontend/                # React 19 + TypeScript + Vite + Tailwind CSS SaaS UI
│   ├── src/
│   │   ├── components/      # Sidebar, Header
│   │   ├── pages/           # Dashboard, DocumentChat, Traces, Evaluations, Costs, Settings
│   │   ├── services/        # Typed API service
│   │   └── types/           # API and telemetry interfaces
│   ├── package.json
│   └── vite.config.ts
├── tests/
│   └── test_main.py         # Pytest test suite with mocks (including restart tests)
├── data/                    # Local persistent storage (gitignored)
├── .env                     # Backend configuration (gitignored)
└── pytest.ini               # Pytest configuration
```

---

## Configuration (`.env`)

In the `ragops/` directory, create or edit `.env`:

```dotenv
GOOGLE_API_KEY=your_gemini_api_key_here
EMBEDDING_MODEL=models/gemini-embedding-001
LLM_MODEL=gemini-3.8-flash
LLM_TEMPERATURE=0.0
INPUT_PRICE_PER_MILLION_TOKENS=0.0
OUTPUT_PRICE_PER_MILLION_TOKENS=0.0
DEFAULT_CHUNK_SIZE=500
DEFAULT_CHUNK_OVERLAP=50
DEFAULT_TOP_K=4
```

Token and cost metrics remain unavailable unless Gemini returns usage metadata
and both pricing variables are configured with the applicable price per
million tokens. The dashboard never substitutes a fabricated cost.

## Evaluation engine

Evaluation datasets are stored under `data/evaluation/`. The included
`dataset.json` is explicitly a development sample and must not be treated as a
production benchmark.

Evaluation endpoints:

```text
GET  /api/evaluations/datasets
POST /api/evaluations/datasets
GET  /api/evaluations/datasets/{dataset_id}?version=1.0.0
POST /api/evaluations/run
GET  /api/evaluations/runs
GET  /api/evaluations/runs/{run_id}
```

The current offline scoring configuration is deterministic:

- **Retrieval relevance**: token overlap between reference context and the
  retrieved chunk text. It measures lexical coverage, not semantic relevance.
- **Faithfulness**: each generated sentence is considered supported when at
  least half of its normalized tokens occur in retrieved context. Unsupported
  sentences are returned separately. This is not an entailment model.
- **Answer correctness**: average of expected-answer token coverage in the
  generated answer and reference context. It is not a human or LLM judgment.
- **Citation accuracy**: validates that the expected source appears among the
  retrieved source metadata. It separately reports missing, invalid, and
  unsupported citation categories where applicable.

Scores are nullable when required inputs are unavailable. Failed cases are
persisted with their error type and message; they are not silently skipped.

## GitHub Actions quality gate

The workflow at `.github/workflows/ragops-ci.yml` runs on pushes and pull
requests targeting `main`, plus manual dispatch. It installs dependencies,
validates the dataset, runs the offline pytest suite, and builds the frontend.
It does not call Gemini or depend on local Chroma/SQLite data.

CI sets `RAGOPS_DATA_DIR`, `RAGOPS_UPLOAD_DIR`, `RAGOPS_CHROMA_PERSIST_DIR`,
and `RAGOPS_SQLITE_DB_PATH` to runner-temporary directories. To reproduce the
same isolation locally in PowerShell:

```powershell
Set-Location D:\RAGops\ragops
$env:RAGOPS_DATA_DIR = Join-Path $env:TEMP "ragops-ci-data"
$env:RAGOPS_UPLOAD_DIR = Join-Path $env:RAGOPS_DATA_DIR "uploads"
$env:RAGOPS_CHROMA_PERSIST_DIR = Join-Path $env:RAGOPS_DATA_DIR "chroma"
$env:RAGOPS_SQLITE_DB_PATH = Join-Path $env:RAGOPS_DATA_DIR "ragops.db"
New-Item -ItemType Directory -Force $env:RAGOPS_UPLOAD_DIR, $env:RAGOPS_CHROMA_PERSIST_DIR
.\.venv\Scripts\python.exe -m pytest -q
```

Quality policy is versioned in `config/rag_quality.json`. The checked-in
configuration intentionally has no minimum thresholds and no baseline because
the included dataset is a development sample. This means CI validates the
test and dataset plumbing without claiming a production quality score.

To enable a reviewed gate, first run a non-sample evaluation against a
controlled test corpus, review every case and metric limitation, then set
`sample_dataset` to `false`, configure `minimum_scores`, and optionally add a
`baseline` plus `maximum_regression` tolerances. Do not copy sample results
into the baseline.

The local gate can validate the current dataset with:

```powershell
Set-Location D:\RAGops\ragops
.\.venv\Scripts\python.exe scripts\quality_gate.py `
  --config config\rag_quality.json `
  --dataset data\evaluation\dataset.json
```

A real evaluation JSON report can be checked explicitly without exposing
secrets:

```powershell
.\.venv\Scripts\python.exe scripts\quality_gate.py `
  --config config\rag_quality.json `
  --dataset data\evaluation\dataset.json `
  --metrics-file path\to\reviewed_metrics.json
```

Missing metrics fail only when a minimum threshold or baseline comparison is
enabled. Dataset/configuration errors return an infrastructure failure rather
than a passing quality result. Live Gemini evaluation is intentionally not
part of ordinary CI; if added later, use a separate workflow and the
repository secret `GOOGLE_API_KEY`, never `.env` or logged command output.

---

## How to Run

### 1. Launch FastAPI Backend

From `ragops/`:
```powershell
.\.venv\Scripts\uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
- API Docs: `http://localhost:8000/docs`
- Readiness check: `http://localhost:8000/api/rag/ready`
- Health check: `http://localhost:8000/health`

### 2. Launch React Frontend

In a separate terminal, from `ragops/frontend/`:
```powershell
npm run dev
```
- Frontend UI: `http://localhost:5175`

### 3. Run Test Suite

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
*(Tests mock out external Gemini calls and include verification of Chroma persistence across restarts)*

### 4. Demo Workflow

1. Start the backend and frontend using the commands above.
2. Open `http://localhost:5175`.
3. Open **Document Chat**, upload a `.txt` or `.pdf` file, and wait for indexing.
4. Open **Document Explorer** to inspect the chunks and metadata stored in ChromaDB.
5. Ask a question in **Document Chat** and inspect the returned source citations.
6. Open **Dashboard**, **Request Traces**, and **Cost Analytics** to inspect the
   recorded request telemetry.
7. Open **Evaluations** to validate the versioned dataset and run an evaluation
   when the indexed corpus and Gemini key are available.

Token usage and estimated cost are intentionally shown as unavailable when the
provider does not return usage metadata or pricing is not configured. The checked
in sample dataset is not a production quality benchmark.

## Security and scope limitations

- This is a local development and portfolio application, not a multi-tenant
  service. There is currently no authentication, authorization, user identity,
  or per-user document namespace. Anyone who can reach the API can list or query
  the shared local collection.
- Uploaded files are restricted to PDF/TXT, limited to 25 MB, sanitized, and
  stored beneath the configured upload directory.
- API keys are read from environment configuration and are not returned by the
  settings endpoint. Do not expose the backend publicly without adding
  authentication, authorization, transport security, and tenant isolation.
- Error details from provider and retrieval failures are recorded for local
  troubleshooting; review and sanitize them before using this service in a
  public environment.

---

## Data Backup and Reset Procedures

### How to Back Up Local Data
To create a snapshot of all indexed documents, vectors, and traces:
```powershell
Copy-Item -Path "data" -Destination "data_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')" -Recurse
```

### How to Clear Local Data Safely
RAGOps never clears the collection automatically. If you intentionally need
to reset local development data:
1. Stop the backend server.
2. Run in PowerShell:
```powershell
# Remove vector index, uploads, and SQLite database
Remove-Item -Path "data\uploads\*", "data\chroma\*", "data\ragops.db" -Recurse -Force -ErrorAction SilentlyContinue
```
3. Restart the backend — it will automatically recreate empty directories and fresh database tables.

---

## Troubleshooting

1. **`Port already in use` error on 5173 / 5175**:
   - Another process may be holding the port. Check active processes with `Get-NetTCPConnection -LocalPort 5175`. The frontend is configured with `strictPort: true` in `vite.config.ts`.
2. **`GOOGLE_API_KEY is not configured`**:
   - Ensure `.env` exists in the `ragops/` root with a valid Google Gemini API key.
3. **ChromaDB Access Denied on Windows**:
   - Ensure no other Python process has locked `data/chroma/chroma.sqlite3`.
