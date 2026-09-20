/**
 * Typed API client. All backend communication goes through this module -
 * components never call fetch() directly.
 */

import type {
  Analysis,
  ApiError,
  AssumptionsPayload,
  BaselinePayload,
  BatchRecord,
  BatchSummaryListItem,
  BottleneckAnalysis,
  DatasetContract,
  DatasetListItem,
  FeatureSpacePayload,
  HumanReviewResponse,
  InspectionSource,
  InvestigationRecord,
  InvestigationSummary,
  MlSummary,
  ProcessTimeline,
  Recommendation,
  RecommendationListResponse,
  RecommendationRun,
  ReviewQueueItem,
  ReviewStats,
  RootCauseAnalysis,
  ScenarioPayload,
  SourceSummary,
  StreamNextResponse,
  StreamStatus,
  VisionInspection,
  VisionInspectionSummary,
  VisionModelStatus,
} from "../types/api";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://127.0.0.1:8000";
export class ApiRequestError extends Error {
  status: number;
  payload: ApiError | null;

  constructor(status: number, payload: ApiError | null, message?: string) {
    super(message ?? payload?.message ?? `Request failed with status ${status}`);
    this.name = "ApiRequestError";
    this.status = status;
    this.payload = payload;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
  } catch {
    throw new ApiRequestError(0, null, `Cannot reach the analysis backend at ${API_BASE}. Is it running?`);
  }

  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    const detail = (body as { detail?: ApiError } | null)?.detail ?? null;
    throw new ApiRequestError(response.status, detail);
  }
  return body as T;
}

export const api = {
  health: () => request<{ status: string; service: string; models_initialized: boolean }>("/api/health"),

  listDatasets: () => request<{ datasets: DatasetListItem[] }>("/api/datasets"),

  getDataset: (datasetId: string) => request<DatasetContract>(`/api/datasets/${datasetId}`),

  getStatus: (datasetId: string) =>
    request<{ dataset_id: string; status: string; stages: Analysis["stages"]; error: ApiError | null }>(
      `/api/datasets/${datasetId}/status`,
    ),

  getAnalysis: (datasetId: string) => request<Analysis>(`/api/datasets/${datasetId}/analysis`),

  getMl: (datasetId: string) =>
    request<{ dataset_id: string; status: string; models: MlSummary["models"]; skipped_inputs: MlSummary["skipped_inputs"]; vision: MlSummary["vision"]; total_training_seconds?: number }>(
      `/api/datasets/${datasetId}/models`,
    ),

  getRootCauseTargets: (datasetId: string) =>
    request<{ dataset_id: string; targets: RootCauseAnalysis["target"][]; count: number }>(
      `/api/datasets/${datasetId}/root-cause/targets`,
    ),

  analyzeRootCause: (datasetId: string, body: { target: string; direction?: string; quantile?: number; input?: string }) =>
    request<RootCauseAnalysis>(`/api/datasets/${datasetId}/root-cause/analyze`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getRootCauseFindings: (datasetId: string) =>
    request<{ dataset_id: string; analyses: Array<Record<string, unknown>>; count: number }>(
      `/api/datasets/${datasetId}/root-cause/findings`,
    ),

  getRootCauseAnalysis: (datasetId: string, analysisId: string) =>
    request<RootCauseAnalysis>(`/api/datasets/${datasetId}/root-cause/${analysisId}`),

  getBottleneckStatus: (datasetId: string) =>
    request<{ dataset_id: string; status: string; reason: string | null; stations_available: number; analyses_run: number; last_analysis_id: string | null }>(
      `/api/datasets/${datasetId}/bottleneck/status`,
    ),

  analyzeBottleneck: (datasetId: string, body: { input?: string } = {}) =>
    request<BottleneckAnalysis>(`/api/datasets/${datasetId}/bottleneck/analyze`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getBottleneckFindings: (datasetId: string) =>
    request<{ dataset_id: string; analyses: Array<Record<string, unknown>>; count: number }>(
      `/api/datasets/${datasetId}/bottleneck/findings`,
    ),

  getBottleneckFlow: (datasetId: string) =>
    request<BottleneckAnalysis["flow"] & { dataset_id: string; analysis_id?: string }>(
      `/api/datasets/${datasetId}/bottleneck/flow`,
    ),

  getBottleneckAnalysis: (datasetId: string, analysisId: string) =>
    request<BottleneckAnalysis>(`/api/datasets/${datasetId}/bottleneck/${analysisId}`),

  getEconomicsStatus: (datasetId: string) =>
    request<{
      dataset_id: string;
      status: string;
      reason: string | null;
      bottleneck_analysis_id: string | null;
      bottleneck_station: string | null;
      throughput_available: boolean;
      assumptions_supplied: string[];
      assumptions_missing: string[];
      currency: string | null;
    }>(`/api/datasets/${datasetId}/economics/status`),

  getAssumptions: (datasetId: string) => request<AssumptionsPayload>(`/api/datasets/${datasetId}/economics/assumptions`),

  putAssumptions: (datasetId: string, updates: Record<string, string | number | null>) =>
    request<AssumptionsPayload>(`/api/datasets/${datasetId}/economics/assumptions`, {
      method: "PUT",
      body: JSON.stringify(updates),
    }),

  getBaseline: (datasetId: string) => request<BaselinePayload>(`/api/datasets/${datasetId}/economics/baseline`),

  runScenario: (
    datasetId: string,
    body: {
      scenario_type: string;
      changes: Record<string, string | number>;
      sensitivity?: { parameter: string; values: number[] };
    },
  ) =>
    request<ScenarioPayload>(`/api/datasets/${datasetId}/economics/scenario`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listScenarios: (datasetId: string) =>
    request<{ dataset_id: string; scenarios: Array<Record<string, unknown>>; count: number }>(
      `/api/datasets/${datasetId}/economics/scenarios`,
    ),

  generateRecommendations: (datasetId: string) =>
    request<RecommendationRun>(`/api/datasets/${datasetId}/recommendations/generate`, { method: "POST" }),

  listRecommendations: (datasetId: string) =>
    request<RecommendationListResponse>(`/api/datasets/${datasetId}/recommendations`),

  getRecommendation: (datasetId: string, recommendationId: string) =>
    request<Recommendation>(`/api/datasets/${datasetId}/recommendations/${recommendationId}`),

  // Phase 12 - vision inspection
  getVisionStatus: () => request<VisionModelStatus>("/api/vision/status"),

  getVisionDataset: () =>
    request<{ dataset_dir: string; fingerprint: string; class_counts: Record<string, number>; annotations: unknown }>(
      "/api/vision/dataset",
    ),

  trainVision: (body: { dataset_dir?: string; use_cached_embeddings?: boolean } = {}) =>
    request<Record<string, unknown>>("/api/vision/train", { method: "POST", body: JSON.stringify(body) }),

  getVisionHistory: () => request<{ inspections: VisionInspectionSummary[]; count: number }>("/api/vision/history"),

  getVisionInspection: (inspectionId: string) => request<VisionInspection>(`/api/vision/inspect/${inspectionId}`),

  getVisionTrace: (inspectionId: string) =>
    request<{ inspection_id: string; stage_count: number; stages: VisionInspection["trace"]; note: string }>(
      `/api/vision/inspect/${inspectionId}/trace`,
    ),

  // --- V2: production stream, feature space, timeline, investigations --------
  streamStatus: () => request<StreamStatus>("/api/vision/stream/status"),

  streamStart: () => request<StreamStatus>("/api/vision/stream/start", { method: "POST" }),

  streamPause: () => request<StreamStatus>("/api/vision/stream/pause", { method: "POST" }),

  streamResume: () => request<StreamStatus>("/api/vision/stream/resume", { method: "POST" }),

  streamReset: () => request<StreamStatus>("/api/vision/stream/reset", { method: "POST" }),

  streamSpeed: (speed: number) =>
    request<StreamStatus>("/api/vision/stream/speed", { method: "POST", body: JSON.stringify({ speed }) }),

  streamNext: () => request<StreamNextResponse>("/api/vision/stream/next", { method: "POST" }),

  getFeatureSpace: () => request<FeatureSpacePayload>("/api/vision/feature-space"),

  getProcessTimeline: (datasetId: string, bins = 48) =>
    request<ProcessTimeline>(`/api/datasets/${datasetId}/process/timeline?bins=${bins}`),

  runInvestigation: (inspectionId: string, datasetId?: string | null) =>
    request<InvestigationRecord>("/api/investigations/run", {
      method: "POST",
      body: JSON.stringify({ inspection_id: inspectionId, dataset_id: datasetId ?? null }),
    }),

  listInvestigations: (limit = 50) =>
    request<{ investigations: InvestigationSummary[]; count: number; note: string }>(
      `/api/investigations?limit=${limit}`,
    ),

  getInvestigation: (investigationId: string) =>
    request<InvestigationRecord>(`/api/investigations/${investigationId}`),

  // --- V2.1: batch / dataset inspection ------------------------------------
  createBatch: async (files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    let response: Response;
    try {
      response = await fetch(`${API_BASE}/api/vision/batch`, { method: "POST", body: form });
    } catch {
      throw new ApiRequestError(0, null, `Cannot reach the analysis backend at ${API_BASE}. Is it running?`);
    }
    const text = await response.text();
    let body: unknown = null;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = null;
      }
    }
    if (!response.ok) {
      throw new ApiRequestError(response.status, (body as { detail?: ApiError })?.detail ?? null);
    }
    return body as BatchRecord;
  },

  inspectBatch: (batchId: string) =>
    request<BatchRecord>(`/api/vision/batch/${batchId}/inspect`, { method: "POST" }),

  getBatch: (batchId: string) => request<BatchRecord>(`/api/vision/batch/${batchId}`),

  listBatches: (limit = 20) => request<{ batches: BatchSummaryListItem[]; count: number }>(`/api/vision/batches?limit=${limit}`),

  getReviewQueue: (includeReviewed = false, limit = 100) =>
    request<{ items: ReviewQueueItem[]; count: number; include_reviewed: boolean }>(
      `/api/vision/review/queue?include_reviewed=${includeReviewed}&limit=${limit}`,
    ),

  getReviewStats: () => request<ReviewStats>("/api/vision/review/stats"),

  reviewAction: (inspectionId: string, action: string, note?: string, className?: string) =>
    request<HumanReviewResponse>(`/api/vision/inspect/${inspectionId}/review`, {
      method: "POST",
      body: JSON.stringify({ action, note: note ?? null, class_name: className ?? null }),
    }),

  // --- V2.3: runtime inspection sources ------------------------------------
  listSources: (limit = 20) => request<{ sources: SourceSummary[]; count: number }>(`/api/inspection/sources?limit=${limit}`),

  getCurrentSource: () => request<{ source: InspectionSource | null; note: string }>("/api/inspection/sources/current"),

  getSource: (sourceId: string) => request<InspectionSource>(`/api/inspection/sources/${sourceId}`),

  createSource: (files: File[], sourceType: string, displayName?: string) => {
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    form.append("source_type", sourceType);
    if (displayName) form.append("display_name", displayName);
    return createSourceUpload(form);
  },

  createDemoSource: () => {
    const form = new FormData();
    form.append("source_type", "BUILT_IN_DEMO");
    return createSourceUpload(form);
  },

  sourceStart: (sourceId: string) => request<StreamStatus>(`/api/inspection/sources/${sourceId}/start`, { method: "POST" }),

  sourceNext: (sourceId: string) => request<StreamNextResponse>(`/api/inspection/sources/${sourceId}/next`, { method: "POST" }),

  sourceReset: (sourceId: string) => request<StreamStatus>(`/api/inspection/sources/${sourceId}/reset`, { method: "POST" }),

  sourcePause: (sourceId: string) => request<StreamStatus>(`/api/inspection/sources/${sourceId}/pause`, { method: "POST" }),

  sourceInspect: (sourceId: string) => request<InspectionSource>(`/api/inspection/sources/${sourceId}/inspect`, { method: "POST" }),

  sourceAddFiles: (sourceId: string, files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    return sourceUpload(form, sourceId);
  },

  deleteSource: (sourceId: string) => request<{ deleted: string; note: string }>(`/api/inspection/sources/${sourceId}`, { method: "DELETE" }),
};

/** Multipart upload helper for source creation (no JSON content-type). */
async function createSourceUpload(form: FormData): Promise<InspectionSource> {
  return multipartRequest<InspectionSource>("/api/inspection/sources", form);
}

/** Multipart upload helper for appending files to a source. */
async function sourceUpload(form: FormData, sourceId: string): Promise<InspectionSource> {
  return multipartRequest<InspectionSource>(`/api/inspection/sources/${sourceId}/files`, form);
}

async function multipartRequest<T>(path: string, form: FormData): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { method: "POST", body: form });
  } catch {
    throw new ApiRequestError(0, null, `Cannot reach the analysis backend at ${API_BASE}. Is it running?`);
  }
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!response.ok) {
    throw new ApiRequestError(response.status, (body as { detail?: ApiError })?.detail ?? null);
  }
  return body as T;
}

export async function inspectImageFile(file: File): Promise<VisionInspection> {
  const form = new FormData();
  form.append("file", file);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/vision/inspect`, { method: "POST", body: form });
  } catch {
    throw new ApiRequestError(0, null, `Cannot reach the analysis backend at ${API_BASE}. Is it running?`);
  }
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!response.ok) {
    throw new ApiRequestError(response.status, (body as { detail?: ApiError })?.detail ?? null);
  }
  return body as VisionInspection;
}

export type VisionStreamEvent =
  | { event: "stage"; stage: VisionInspection["trace"][number] }
  | { event: "result"; result: VisionInspection }
  | { event: "error"; error: ApiError };

/**
 * Stream the inspection: the backend emits each stage the moment it completes.
 * The callback receives live stage events, then the final result event.
 */
export async function inspectImageStream(
  file: File,
  onEvent: (event: VisionStreamEvent) => void,
): Promise<VisionInspection | null> {
  const form = new FormData();
  form.append("file", file);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/vision/inspect/stream`, { method: "POST", body: form });
  } catch {
    throw new ApiRequestError(0, null, `Cannot reach the analysis backend at ${API_BASE}. Is it running?`);
  }
  if (!response.ok) {
    const text = await response.text();
    let body: unknown = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = null;
    }
    throw new ApiRequestError(response.status, (body as { detail?: ApiError })?.detail ?? null);
  }
  if (!response.body) {
    throw new ApiRequestError(0, null, "Streaming is not supported by this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: VisionInspection | null = null;

  const handleLine = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    let payload: VisionStreamEvent;
    try {
      payload = JSON.parse(trimmed) as VisionStreamEvent;
    } catch {
      return;
    }
    if (payload.event === "result") {
      result = payload.result;
    } else if (payload.event === "error") {
      throw new ApiRequestError(503, payload.error);
    }
    onEvent(payload);
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index = buffer.indexOf("\n");
    while (index >= 0) {
      const line = buffer.slice(0, index);
      buffer = buffer.slice(index + 1);
      handleLine(line);
      index = buffer.indexOf("\n");
    }
  }
  if (buffer.trim()) handleLine(buffer);
  return result;
}

export { API_BASE };
