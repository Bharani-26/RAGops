import {
  DocumentUploadResponse,
  QueryRequest,
  QueryResponse,
  IndexedDocument,
  RequestTrace,
  MetricsSummary,
  EvaluationRun,
  AppSettings,
  ObservabilityOverview,
  ObservabilityRequest,
  RequestDetail,
  LatencyMetrics,
  ErrorMetrics,
  CostMetrics,
  EvaluationDataset,
  EvaluationRunDetail,
} from "../types/api";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

class ApiService {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  async checkHealth(): Promise<{ status: string }> {
    const res = await fetch(`${this.baseUrl}/health`);
    if (!res.ok) throw new Error(`Health check failed with status ${res.status}`);
    return res.json();
  }

  async uploadDocument(
    file: File,
    chunkSize?: number,
    chunkOverlap?: number
  ): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append("file", file);
    if (chunkSize !== undefined) formData.append("chunk_size", chunkSize.toString());
    if (chunkOverlap !== undefined) formData.append("chunk_overlap", chunkOverlap.toString());

    const res = await fetch(`${this.baseUrl}/api/rag/upload`, {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      let errorMsg = `Upload failed (${res.status})`;
      try {
        const errJson = await res.json();
        if (errJson.detail) errorMsg = errJson.detail;
      } catch {
        // use fallback
      }
      throw new Error(errorMsg);
    }

    return res.json();
  }

  async listDocuments(): Promise<IndexedDocument[]> {
    const res = await fetch(`${this.baseUrl}/api/rag/documents`);
    if (!res.ok) throw new Error("Failed to fetch documents");
    const data = await res.json();
    return data.documents || [];
  }

  async queryRag(payload: QueryRequest): Promise<QueryResponse> {
    const res = await fetch(`${this.baseUrl}/api/rag/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      let errorMsg = `Query failed (${res.status})`;
      try {
        const errJson = await res.json();
        if (errJson.detail) errorMsg = errJson.detail;
      } catch {
        // fallback
      }
      throw new Error(errorMsg);
    }

    return res.json();
  }

  async getTraces(): Promise<RequestTrace[]> {
    const res = await fetch(`${this.baseUrl}/api/rag/traces`);
    if (!res.ok) throw new Error("Failed to fetch traces");
    const data = await res.json();
    return data.traces || [];
  }

  async getMetrics(): Promise<MetricsSummary> {
    const res = await fetch(`${this.baseUrl}/api/rag/metrics`);
    if (!res.ok) throw new Error("Failed to fetch metrics");
    return res.json();
  }

  async getEvaluations(): Promise<EvaluationRun[]> {
    const res = await fetch(`${this.baseUrl}/api/rag/evaluations`);
    if (!res.ok) throw new Error("Failed to fetch evaluations");
    const data = await res.json();
    return data.evaluations || [];
  }

  async getSettings(): Promise<AppSettings> {
    const res = await fetch(`${this.baseUrl}/api/rag/settings`);
    if (!res.ok) throw new Error("Failed to fetch settings");
    return res.json();
  }

  async getObservabilityOverview(params = ""): Promise<ObservabilityOverview> {
    const res = await fetch(`${this.baseUrl}/api/observability/overview${params}`);
    if (!res.ok) throw new Error("Failed to fetch observability overview");
    return res.json();
  }

  async getObservabilityRequests(params = ""): Promise<{ total: number; requests: ObservabilityRequest[] }> {
    const res = await fetch(`${this.baseUrl}/api/observability/requests${params}`);
    if (!res.ok) throw new Error("Failed to fetch request history");
    return res.json();
  }

  async getObservabilityRequest(requestId: string): Promise<RequestDetail> {
    const res = await fetch(`${this.baseUrl}/api/observability/requests/${requestId}`);
    if (!res.ok) throw new Error("Failed to fetch request detail");
    return res.json();
  }

  async getLatencyMetrics(params = ""): Promise<LatencyMetrics> {
    const res = await fetch(`${this.baseUrl}/api/observability/latency${params}`);
    if (!res.ok) throw new Error("Failed to fetch latency metrics");
    return res.json();
  }

  async getErrorMetrics(params = ""): Promise<ErrorMetrics> {
    const res = await fetch(`${this.baseUrl}/api/observability/errors${params}`);
    if (!res.ok) throw new Error("Failed to fetch error metrics");
    return res.json();
  }

  async getCostMetrics(params = ""): Promise<CostMetrics> {
    const res = await fetch(`${this.baseUrl}/api/observability/costs${params}`);
    if (!res.ok) throw new Error("Failed to fetch cost metrics");
    return res.json();
  }

  async getEvaluationDatasets(): Promise<EvaluationDataset[]> {
    const res = await fetch(`${this.baseUrl}/api/evaluations/datasets`);
    if (!res.ok) throw new Error("Failed to fetch evaluation datasets");
    return (await res.json()).datasets || [];
  }

  async runEvaluation(datasetId: string, version?: string): Promise<EvaluationRunDetail> {
    const res = await fetch(`${this.baseUrl}/api/evaluations/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_id: datasetId, version }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Evaluation run failed");
    }
    return res.json();
  }

  async getEvaluationRuns(): Promise<EvaluationRun[]> {
    const res = await fetch(`${this.baseUrl}/api/evaluations/runs`);
    if (!res.ok) throw new Error("Failed to fetch evaluation runs");
    return (await res.json()).runs || [];
  }

  async getEvaluationRun(runId: string): Promise<EvaluationRunDetail> {
    const res = await fetch(`${this.baseUrl}/api/evaluations/runs/${runId}`);
    if (!res.ok) throw new Error("Failed to fetch evaluation run");
    return res.json();
  }
}

export const api = new ApiService(API_BASE_URL);
