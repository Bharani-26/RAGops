export interface ChunkMetadata {
  source: string;
  chunk_index: number;
  total_chunks: number;
  page_number?: number;
  chunk_id?: string;
  citation?: string;
  content_preview: string;
  metadata: Record<string, any>;
}

export interface DocumentUploadResponse {
  message: string;
  filename: string;
  doc_id: string;
  total_chunks: number;
  chunk_ids: string[];
}

export interface QueryRequest {
  query: string;
  top_k?: number;
}

export interface QueryResponse {
  request_id: string;
  query: string;
  answer: string;
  sources: ChunkMetadata[];
}

export interface IndexedDocument {
  document_id?: string;
  doc_id?: string;
  filename: string;
  server_filename?: string;
  chunk_count?: number;
  size_bytes: number;
  modified_at: number;
}

export interface StoredChunk {
  chunk_id: string | null;
  document_id: string | null;
  filename: string;
  page_number?: number | null;
  metadata: Record<string, unknown>;
  text: string;
}

export interface ChunkDocumentSummary {
  document_id: string;
  filename: string;
  chunk_count: number;
}

export interface ChunkExplorerResponse {
  chunks: StoredChunk[];
  documents: ChunkDocumentSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface TraceStage {
  name: string;
  duration_ms?: number;
  status: string;
  details?: string;
  error?: string;
}

export interface RequestTrace {
  id: string;
  timestamp: number;
  query: string;
  answer: string;
  model: string;
  latency_ms: number;
  status_code: number;
  status: string;
  top_k: number;
  source_count: number;
  sources: ChunkMetadata[];
  stages: TraceStage[];
  estimated_cost: number | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  error_type?: string | null;
  error_message?: string | null;
}

export interface MetricsSummary {
  total_requests: number;
  p95_latency_ms: number;
  avg_latency_ms: number;
  error_rate: number;
  total_cost: number | null;
}

export interface ObservabilityOverview {
  total_requests: number;
  success_count: number;
  failure_count: number;
  success_rate: number;
  average_latency_ms: number | null;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  estimated_cost: number | null;
  cost_available: boolean;
  token_usage_available: boolean;
}

export interface ObservabilityRequest extends RequestTrace {
  retrieved_chunks: number;
  request_id: string;
}

export interface RequestStage {
  name: string;
  duration_ms: number;
  status: string;
  details?: string | null;
}

export interface RequestDetail extends Omit<ObservabilityRequest, "stages"> {
  stages: RequestStage[];
  errors: Array<{ error_type: string; message: string; timestamp: number }>;
}

export interface LatencyMetrics {
  points: Array<{ timestamp: number; latency_ms: number; retrieved_chunks: number }>;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
}

export interface ErrorMetrics {
  errors: Array<{
    error_type: string;
    count: number;
    recent: Array<{ request_id: string; message: string; timestamp: number }>;
  }>;
  total: number;
}

export interface CostMetrics {
  points: Array<{
    timestamp: number;
    input_tokens: number | null;
    output_tokens: number | null;
    estimated_cost: number | null;
  }>;
  total_estimated_cost: number | null;
  total_input_tokens: number | null;
  total_output_tokens: number | null;
  cost_available: boolean;
}

export interface EvaluationRun {
  id: string;
  run_id?: string;
  timestamp: number;
  retrieval_relevance?: number | null;
  faithfulness?: number | null;
  answer_correctness?: number | null;
  citation_accuracy?: number | null;
  dataset_name: string;
  dataset_id?: string;
  dataset_version?: string;
  total_samples?: number;
  completed_samples?: number;
  failed_samples?: number;
  status?: string;
}

export interface EvaluationCase {
  id: string;
  question: string;
  expected_answer: string;
  reference_context: string;
  expected_source?: string;
  tags?: string[];
}

export interface EvaluationDataset {
  dataset_id: string;
  version: string;
  name: string;
  description: string;
  sample: boolean;
  cases: EvaluationCase[];
}

export interface EvaluationRunDetail extends EvaluationRun {
  run_id: string;
  avg_relevance: number | null;
  avg_faithfulness: number | null;
  avg_correctness: number | null;
  avg_citation_precision: number | null;
  results: Array<{
    id: string;
    test_case_id: string;
    question: string;
    ground_truth: string;
    reference_context: string;
    generated_answer: string;
    retrieved_chunks: Array<{ content: string; metadata: Record<string, unknown> }>;
    citations: Array<Record<string, unknown>>;
    relevance_score: number | null;
    faithfulness_score: number | null;
    correctness_score: number | null;
    citation_score: number | null;
    unsupported_claims: string[];
    citation_details: Record<string, unknown>;
    status: string;
    error_type?: string;
    error_message?: string;
  }>;
}

export interface AppSettings {
  project_name: string;
  api_key_configured: boolean;
  embedding_model: string;
  llm_model: string;
  temperature: number;
  default_chunk_size: number;
  default_chunk_overlap: number;
  default_top_k: number;
  chroma_collection: string;
}
