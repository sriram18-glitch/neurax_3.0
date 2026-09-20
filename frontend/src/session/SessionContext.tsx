/**
 * Dataset + automation session store.
 *
 * All judge-visible values flow through this reducer from the typed API client.
 * No component may hold result data of its own - everything comes from here.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, type ReactNode } from "react";

import { api, ApiRequestError, API_BASE, inspectImageStream, type VisionStreamEvent } from "../api/client";
import type {
  Analysis,
  ApiError,
  AssumptionsPayload,
  BaselinePayload,
  BatchRecord,
  BatchSummaryListItem,
  BottleneckAnalysis,
  Coverage,
  DatasetContract,
  DatasetListItem,
  FeatureSpacePayload,
  HumanReviewResponse,
  InspectionSource,
  InvestigationRecord,
  InvestigationSummary,
  MlSummary,
  ProcessTimeline,
  RecommendationListResponse,
  RecommendationRun,
  ReviewQueueItem,
  ReviewStats,
  RootCauseAnalysis,
  ScenarioPayload,
  SourceSummary,
  StreamStatus,
  VisionInspection,
  VisionInspectionSummary,
  VisionModelStatus,
  VisionTraceStage,
} from "../types/api";

export type AppPhase = "empty" | "uploading" | "processing" | "ready" | "error";

export interface SessionState {
  phase: AppPhase;
  datasets: DatasetListItem[];
  datasetId: string | null;
  contract: DatasetContract | null;
  analysis: Analysis | null;
  ml: MlSummary | null;
  rootCause: RootCauseAnalysis | null;
  bottleneck: BottleneckAnalysis | null;
  assumptions: AssumptionsPayload | null;
  baseline: BaselinePayload | null;
  scenario: ScenarioPayload | null;
  recommendations: RecommendationListResponse | null;
  recommendationRun: RecommendationRun | null;
  error: ApiError | null;
  errorStage: string | null;
  busy: string | null;
  uploadFilename: string | null;
  uploadSize: number | null;
  backendOnline: boolean | null;
  visionStatus: VisionModelStatus | null;
  inspection: VisionInspection | null;
  inspectionHistory: VisionInspectionSummary[];
  inspecting: boolean;
  liveStages: VisionTraceStage[];
  liveStatus: "idle" | "streaming" | "complete" | "error";
  liveImageUrl: string | null;
  cinematic: boolean;
  // V2 automation
  stream: StreamStatus | null;
  streamBusy: boolean;
  streamError: ApiError | null;
  autoInvestigation: boolean;
  investigations: InvestigationSummary[];
  investigation: InvestigationRecord | null;
  investigating: boolean;
  featureSpace: FeatureSpacePayload | null;
  timeline: ProcessTimeline | null;
  timelineBusy: boolean;
  // V2.1 batch + review
  batch: BatchRecord | null;
  batches: BatchSummaryListItem[];
  batchBusy: boolean;
  batchError: ApiError | null;
  reviewQueue: ReviewQueueItem[];
  reviewStats: ReviewStats | null;
  reviewBusy: boolean;
  reviewLastAction: HumanReviewResponse | null;
  // V2.3 runtime inspection sources
  sources: SourceSummary[];
  currentSource: InspectionSource | null;
  sourceBusy: boolean;
}

const initialState: SessionState = {
  phase: "empty",
  datasets: [],
  datasetId: null,
  contract: null,
  analysis: null,
  ml: null,
  rootCause: null,
  bottleneck: null,
  assumptions: null,
  baseline: null,
  scenario: null,
  recommendations: null,
  recommendationRun: null,
  error: null,
  errorStage: null,
  busy: null,
  uploadFilename: null,
  uploadSize: null,
  backendOnline: null,
  visionStatus: null,
  inspection: null,
  inspectionHistory: [],
  inspecting: false,
  liveStages: [],
  liveStatus: "idle",
  liveImageUrl: null,
  cinematic: true,
  stream: null,
  streamBusy: false,
  streamError: null,
  autoInvestigation: true,
  investigations: [],
  investigation: null,
  investigating: false,
  featureSpace: null,
  timeline: null,
  timelineBusy: false,
  batch: null,
  batches: [],
  batchBusy: false,
  batchError: null,
  reviewQueue: [],
  reviewStats: null,
  reviewBusy: false,
  reviewLastAction: null,
  sources: [],
  currentSource: null,
  sourceBusy: false,
};

type Action =
  | { type: "reset" }
  | { type: "datasets"; datasets: DatasetListItem[] }
  | { type: "backend"; online: boolean }
  | { type: "upload_start"; filename: string; size: number }
  | { type: "dataset_loaded"; contract: DatasetContract; analysis: Analysis; ml: MlSummary }
  | { type: "root_cause"; rootCause: RootCauseAnalysis }
  | { type: "bottleneck"; bottleneck: BottleneckAnalysis }
  | { type: "assumptions"; assumptions: AssumptionsPayload }
  | { type: "baseline"; baseline: BaselinePayload }
  | { type: "scenario"; scenario: ScenarioPayload }
  | { type: "recommendations"; recommendations: RecommendationListResponse; run: RecommendationRun | null }
  | { type: "busy"; busy: string | null }
  | { type: "error"; error: ApiError; stage: string }
  | { type: "vision_status"; visionStatus: VisionModelStatus }
  | { type: "inspection"; inspection: VisionInspection }
  | { type: "inspection_history"; history: VisionInspectionSummary[] }
  | { type: "inspecting"; inspecting: boolean }
  | { type: "stream_start"; imageUrl: string }
  | { type: "stream_stage"; stage: VisionTraceStage }
  | { type: "stream_status"; status: SessionState["liveStatus"] }
  | { type: "cinematic"; cinematic: boolean }
  | { type: "stream"; stream: StreamStatus }
  | { type: "stream_busy"; busy: boolean }
  | { type: "stream_error"; error: ApiError | null }
  | { type: "auto_investigation"; enabled: boolean }
  | { type: "investigations"; investigations: InvestigationSummary[] }
  | { type: "investigation"; investigation: InvestigationRecord | null }
  | { type: "investigating"; investigating: boolean }
  | { type: "feature_space"; featureSpace: FeatureSpacePayload | null }
  | { type: "timeline"; timeline: ProcessTimeline | null }
  | { type: "timeline_busy"; busy: boolean }
  | { type: "batch"; batch: BatchRecord | null }
  | { type: "batches"; batches: BatchSummaryListItem[] }
  | { type: "batch_busy"; busy: boolean }
  | { type: "batch_error"; error: ApiError | null }
  | { type: "review_queue"; queue: ReviewQueueItem[] }
  | { type: "review_stats"; stats: ReviewStats | null }
  | { type: "review_busy"; busy: boolean }
  | { type: "review_action"; response: HumanReviewResponse }
  | { type: "sources"; sources: SourceSummary[] }
  | { type: "current_source"; source: InspectionSource | null }
  | { type: "source_busy"; busy: boolean };

function reducer(state: SessionState, action: Action): SessionState {
  switch (action.type) {
    case "reset":
      return { ...initialState, datasets: state.datasets, backendOnline: state.backendOnline, stream: state.stream, investigations: state.investigations, featureSpace: state.featureSpace, autoInvestigation: state.autoInvestigation };
    case "datasets":
      return { ...state, datasets: action.datasets, backendOnline: true };
    case "backend":
      return { ...state, backendOnline: action.online };
    case "upload_start":
      return { ...state, phase: "uploading", uploadFilename: action.filename, uploadSize: action.size, error: null, errorStage: null };
    case "dataset_loaded":
      return {
        ...state,
        phase: "ready",
        datasetId: action.contract.dataset_id,
        contract: action.contract,
        analysis: action.analysis,
        ml: action.ml,
        error: null,
        errorStage: null,
        uploadFilename: null,
        uploadSize: null,
        timeline: null,
      };
    case "root_cause":
      return { ...state, rootCause: action.rootCause };
    case "bottleneck":
      return { ...state, bottleneck: action.bottleneck };
    case "assumptions":
      return { ...state, assumptions: action.assumptions };
    case "baseline":
      return { ...state, baseline: action.baseline };
    case "scenario":
      return { ...state, scenario: action.scenario };
    case "recommendations":
      return { ...state, recommendations: action.recommendations, recommendationRun: action.run };
    case "busy":
      return { ...state, busy: action.busy };
    case "vision_status":
      return { ...state, visionStatus: action.visionStatus };
    case "inspection":
      return { ...state, inspection: action.inspection, inspecting: false, liveStatus: "complete" };
    case "inspection_history":
      return { ...state, inspectionHistory: action.history };
    case "inspecting":
      return { ...state, inspecting: action.inspecting };
    case "stream_start":
      return { ...state, liveStages: [], liveStatus: "streaming", inspecting: true, liveImageUrl: action.imageUrl };
    case "stream_stage":
      return { ...state, liveStages: [...state.liveStages, action.stage] };
    case "stream_status":
      return { ...state, liveStatus: action.status };
    case "cinematic":
      return { ...state, cinematic: action.cinematic };
    case "stream":
      return { ...state, stream: action.stream, streamError: null, streamBusy: false };
    case "stream_busy":
      return { ...state, streamBusy: action.busy };
    case "stream_error":
      return { ...state, streamError: action.error, streamBusy: false };
    case "auto_investigation":
      return { ...state, autoInvestigation: action.enabled };
    case "investigations":
      return { ...state, investigations: action.investigations };
    case "investigation":
      return { ...state, investigation: action.investigation, investigating: false };
    case "investigating":
      return { ...state, investigating: action.investigating };
    case "feature_space":
      return { ...state, featureSpace: action.featureSpace };
    case "timeline":
      return { ...state, timeline: action.timeline, timelineBusy: false };
    case "timeline_busy":
      return { ...state, timelineBusy: action.busy };
    case "batch":
      return { ...state, batch: action.batch, batchBusy: false, batchError: null };
    case "batches":
      return { ...state, batches: action.batches };
    case "batch_busy":
      return { ...state, batchBusy: action.busy };
    case "batch_error":
      return { ...state, batchError: action.error, batchBusy: false };
    case "review_queue":
      return { ...state, reviewQueue: action.queue };
    case "review_stats":
      return { ...state, reviewStats: action.stats };
    case "review_busy":
      return { ...state, reviewBusy: action.busy };
    case "review_action":
      return { ...state, reviewLastAction: action.response, reviewBusy: false };
    case "sources":
      return { ...state, sources: action.sources };
    case "current_source":
      return { ...state, currentSource: action.source, sourceBusy: false };
    case "source_busy":
      return { ...state, sourceBusy: action.busy };
    case "error":
      return { ...state, phase: "error", error: action.error, errorStage: action.stage, busy: null };
    default:
      return state;
  }
}

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiRequestError) {
    return (
      error.payload ?? {
        error: true,
        code: `HTTP_${error.status}`,
        message: error.message,
        detail: null,
      }
    );
  }
  return {
    error: true,
    code: "UNEXPECTED",
    message: error instanceof Error ? error.message : "Unexpected error",
    detail: null,
  };
}

export interface SessionContextValue extends SessionState {
  apiBase: string;
  uploadFile: (file: File) => Promise<void>;
  loadDataset: (datasetId: string) => Promise<void>;
  refreshDatasets: () => Promise<void>;
  runRootCause: (target: string, direction: string, quantile: number) => Promise<void>;
  runBottleneck: () => Promise<void>;
  saveAssumptions: (updates: Record<string, string | number | null>) => Promise<void>;
  refreshBaseline: () => Promise<void>;
  runScenario: (scenarioType: string, changes: Record<string, string | number>, sensitivity?: { parameter: string; values: number[] }) => Promise<void>;
  generateRecommendations: () => Promise<void>;
  refreshRecommendations: () => Promise<void>;
  reset: () => void;
  inspectFile: (file: File) => Promise<VisionInspection | null>;
  refreshVision: () => Promise<void>;
  trainVisionModel: () => Promise<void>;
  loadInspection: (inspectionId: string) => Promise<void>;
  setCinematic: (value: boolean) => void;
  // V2 automation
  refreshStream: () => Promise<void>;
  startStream: () => Promise<void>;
  pauseStream: () => Promise<void>;
  resetStream: () => Promise<void>;
  setStreamSpeed: (speed: number) => Promise<void>;
  processNextFrame: () => Promise<VisionInspection | null>;
  setAutoInvestigation: (value: boolean) => void;
  runInvestigationFor: (inspectionId: string) => Promise<InvestigationRecord | null>;
  refreshInvestigations: () => Promise<void>;
  loadInvestigation: (investigationId: string) => Promise<InvestigationRecord | null>;
  refreshFeatureSpace: () => Promise<void>;
  refreshTimeline: () => Promise<void>;
  // V2.1 batch + review
  createBatch: (files: File[]) => Promise<BatchRecord | null>;
  inspectBatch: (batchId: string) => Promise<void>;
  refreshBatch: (batchId: string) => Promise<BatchRecord | null>;
  refreshBatches: () => Promise<void>;
  resetBatch: () => void;
  refreshReview: () => Promise<void>;
  reviewAction: (inspectionId: string, action: string, note?: string, className?: string) => Promise<void>;
  // V2.3 runtime inspection sources
  refreshSources: () => Promise<void>;
  createSource: (files: File[], sourceType: string, displayName?: string) => Promise<InspectionSource | null>;
  createDemoSource: () => Promise<InspectionSource | null>;
  changeSource: (sourceId: string) => Promise<void>;
  deleteSource: (sourceId: string) => Promise<void>;
}
const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  const withBusy = useCallback(
    async <T,>(label: string, stage: string, fn: () => Promise<T>): Promise<T | null> => {
      dispatch({ type: "busy", busy: label });
      try {
        return await fn();
      } catch (error) {
        dispatch({ type: "error", error: toApiError(error), stage });
        return null;
      } finally {
        dispatch({ type: "busy", busy: null });
      }
    },
    [],
  );

  const refreshDatasets = useCallback(async () => {
    const result = await withBusy("Loading datasets", "datasets", () => api.listDatasets());
    if (result) dispatch({ type: "datasets", datasets: result.datasets });
  }, [withBusy]);

  const loadDataset = useCallback(
    async (datasetId: string) => {
      dispatch({ type: "reset" });
      const result = await withBusy("Loading dataset session", "ingestion", async () => {
        const [contract, analysis, ml] = await Promise.all([
          api.getDataset(datasetId),
          api.getAnalysis(datasetId),
          api.getMl(datasetId),
        ]);
        return { contract, analysis, ml };
      });
      if (!result) return;
      dispatch({ type: "dataset_loaded", ...result });

      const bottleneck = await withBusy("Loading bottleneck analysis", "bottleneck", async () => {
        const findings = await api.getBottleneckFindings(datasetId);
        if (!findings.count) return null;
        const analyses = findings.analyses as Array<{ analysis_id: string }>;
        return api.getBottleneckAnalysis(datasetId, analyses[analyses.length - 1].analysis_id);
      });
      if (bottleneck) dispatch({ type: "bottleneck", bottleneck });

      // economics: load whatever the user already supplied (best effort)
      const economics = await Promise.all([
        api.getAssumptions(datasetId).catch(() => null),
        api.getBaseline(datasetId).catch(() => null),
      ]);
      if (economics[0]) dispatch({ type: "assumptions", assumptions: economics[0] });
      if (economics[1]) dispatch({ type: "baseline", baseline: economics[1] });

      const recommendations = await withBusy("Loading recommendations", "recommendations", async () => {
        const list = await api.listRecommendations(datasetId);
        return list.count ? list : null;
      });
      if (recommendations) dispatch({ type: "recommendations", recommendations, run: null });
    },
    [withBusy],
  );

  const uploadFile = useCallback(
    async (file: File) => {
      dispatch({ type: "upload_start", filename: file.name, size: file.size });
      dispatch({ type: "busy", busy: "Uploading dataset" });
      try {
        const form = new FormData();
        form.append("file", file);
        const response = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: form });
        const text = await response.text();
        const body = text ? JSON.parse(text) : null;
        if (!response.ok) {
          throw new ApiRequestError(response.status, (body as { detail?: ApiError })?.detail ?? null);
        }
        const contract = body as DatasetContract;
        dispatch({ type: "busy", busy: "Loading pipeline results" });
        const [analysis, ml] = await Promise.all([api.getAnalysis(contract.dataset_id), api.getMl(contract.dataset_id)]);
        dispatch({ type: "dataset_loaded", contract, analysis, ml });
        await refreshDatasets();
      } catch (error) {
        dispatch({ type: "error", error: toApiError(error), stage: "ingestion" });
      } finally {
        dispatch({ type: "busy", busy: null });
      }
    },
    [refreshDatasets],
  );

  const runRootCause = useCallback(
    async (target: string, direction: string, quantile: number) => {
      if (!state.datasetId) return;
      const result = await withBusy("Running root-cause analysis", "root_cause", () =>
        api.analyzeRootCause(state.datasetId as string, { target, direction, quantile }),
      );
      if (result) dispatch({ type: "root_cause", rootCause: result });
    },
    [state.datasetId, withBusy],
  );

  const runBottleneck = useCallback(async () => {
    if (!state.datasetId) return;
    const result = await withBusy("Running bottleneck analysis", "bottleneck", () =>
      api.analyzeBottleneck(state.datasetId as string),
    );
    if (result) dispatch({ type: "bottleneck", bottleneck: result });
  }, [state.datasetId, withBusy]);

  const saveAssumptions = useCallback(
    async (updates: Record<string, string | number | null>) => {
      if (!state.datasetId) return;
      const result = await withBusy("Saving assumptions", "economics", () =>
        api.putAssumptions(state.datasetId as string, updates),
      );
      if (result) {
        dispatch({ type: "assumptions", assumptions: result });
        const baseline = await api.getBaseline(state.datasetId as string);
        dispatch({ type: "baseline", baseline });
      }
    },
    [state.datasetId, withBusy],
  );

  const refreshBaseline = useCallback(async () => {
    if (!state.datasetId) return;
    const result = await withBusy("Computing baseline", "economics", () => api.getBaseline(state.datasetId as string));
    if (result) dispatch({ type: "baseline", baseline: result });
  }, [state.datasetId, withBusy]);

  const runScenario = useCallback(
    async (scenarioType: string, changes: Record<string, string | number>, sensitivity?: { parameter: string; values: number[] }) => {
      if (!state.datasetId) return;
      const result = await withBusy("Running scenario", "economics", () =>
        api.runScenario(state.datasetId as string, { scenario_type: scenarioType, changes, sensitivity }),
      );
      if (result) dispatch({ type: "scenario", scenario: result });
    },
    [state.datasetId, withBusy],
  );

  const generateRecommendations = useCallback(async () => {
    if (!state.datasetId) return;
    const run = await withBusy("Generating recommendations", "recommendations", () =>
      api.generateRecommendations(state.datasetId as string),
    );
    if (!run) return;
    const list = await api.listRecommendations(state.datasetId);
    dispatch({ type: "recommendations", recommendations: list, run });
  }, [state.datasetId, withBusy]);

  const refreshRecommendations = useCallback(async () => {
    if (!state.datasetId) return;
    const list = await withBusy("Loading recommendations", "recommendations", () =>
      api.listRecommendations(state.datasetId as string),
    );
    if (list) dispatch({ type: "recommendations", recommendations: list, run: null });
  }, [state.datasetId, withBusy]);

  const reset = useCallback(() => dispatch({ type: "reset" }), []);

  const refreshVision = useCallback(async () => {
    try {
      const [status, history] = await Promise.all([api.getVisionStatus(), api.getVisionHistory()]);
      dispatch({ type: "vision_status", visionStatus: status });
      dispatch({ type: "inspection_history", history: history.inspections });
    } catch {
      /* backend may be offline; the vision area renders its honest empty state */
    }
  }, []);

  const cinematicRef = useRef(state.cinematic);
  const setCinematic = useCallback((value: boolean) => {
    cinematicRef.current = value;
    dispatch({ type: "cinematic", cinematic: value });
  }, []);

  const inspectFile = useCallback(async (file: File): Promise<VisionInspection | null> => {
    const imageUrl = URL.createObjectURL(file);
    dispatch({ type: "stream_start", imageUrl });
    const queue: VisionTraceStage[] = [];
    let finished = false;
    let streamError: unknown = null;
    let finalResult: VisionInspection | null = null;

    // Playback loop: stage data is delivered live by the backend; the UI holds
    // each completed stage briefly so operators can read it (cinematic pacing,
    // display only). Turning pacing off shows raw backend speed.
    const playback = (async () => {
      while (!finished || queue.length > 0) {
        if (queue.length === 0) {
          await new Promise((resolve) => setTimeout(resolve, 40));
          continue;
        }
        const stage = queue.shift() as VisionTraceStage;
        dispatch({ type: "stream_stage", stage });
        if (cinematicRef.current) {
          await new Promise((resolve) => setTimeout(resolve, 750));
        }
      }
    })();

    try {
      const result = await inspectImageStream(file, (event: VisionStreamEvent) => {
        if (event.event === "stage") {
          queue.push(event.stage);
        } else if (event.event === "result") {
          finalResult = event.result;
        }
      });
      finalResult = result;
    } catch (error) {
      streamError = error;
    }
    finished = true;
    await playback;

    if (streamError || !finalResult) {
      dispatch({ type: "stream_status", status: "error" });
      dispatch({ type: "error", error: toApiError(streamError ?? new Error("Inspection failed")), stage: "vision_inspect" });
      dispatch({ type: "inspecting", inspecting: false });
      return null;
    }

    dispatch({ type: "inspection", inspection: finalResult });
    const history = await api.getVisionHistory();
    dispatch({ type: "inspection_history", history: history.inspections });
    return finalResult;
  }, []);

  const loadInspection = useCallback(async (inspectionId: string) => {
    try {
      const result = await api.getVisionInspection(inspectionId);
      dispatch({ type: "stream_start", imageUrl: `${API_BASE}/api/vision/inspect/${inspectionId}/image` });
      dispatch({ type: "stream_status", status: "complete" });
      dispatch({ type: "inspection", inspection: result });
      for (const stage of result.trace) {
        dispatch({ type: "stream_stage", stage });
      }
    } catch (error) {
      dispatch({ type: "error", error: toApiError(error), stage: "vision_history" });
    }
  }, []);

  const trainVisionModel = useCallback(async () => {
    const result = await withBusy("Training vision model", "vision_train", () => api.trainVision());
    if (result) {
      await refreshVision();
      void api.getFeatureSpace().then((payload) => dispatch({ type: "feature_space", featureSpace: payload })).catch(() => undefined);
    }
  }, [withBusy, refreshVision]);

  // ------------------------------------------------------------------
  // V2 automation
  // ------------------------------------------------------------------

  const refreshStream = useCallback(async () => {
    try {
      const [status, current] = await Promise.all([api.streamStatus(), api.getCurrentSource()]);
      dispatch({ type: "stream", stream: status });
      dispatch({ type: "current_source", source: current.source });
    } catch {
      /* backend offline: the stream panel renders its honest state */
    }
  }, []);

  const refreshSources = useCallback(async () => {
    try {
      const list = await api.listSources();
      dispatch({ type: "sources", sources: list.sources });
    } catch {
      /* backend offline */
    }
  }, []);

  const createSource = useCallback(
    async (files: File[], sourceType: string, displayName?: string): Promise<InspectionSource | null> => {
      dispatch({ type: "source_busy", busy: true });
      try {
        const record = await api.createSource(files, sourceType, displayName);
        dispatch({ type: "batch", batch: record });
        dispatch({ type: "current_source", source: record });
        await refreshSources();
        await refreshStream();
        return record;
      } catch (error) {
        dispatch({ type: "batch_error", error: toApiError(error) });
        dispatch({ type: "source_busy", busy: false });
        return null;
      }
    },
    [refreshSources, refreshStream],
  );

  const createDemoSource = useCallback(async (): Promise<InspectionSource | null> => {
    dispatch({ type: "source_busy", busy: true });
    try {
      const record = await api.createDemoSource();
      dispatch({ type: "batch", batch: record });
      dispatch({ type: "current_source", source: record });
      await refreshSources();
      await refreshStream();
      return record;
    } catch (error) {
      dispatch({ type: "batch_error", error: toApiError(error) });
      dispatch({ type: "source_busy", busy: false });
      return null;
    }
  }, [refreshSources, refreshStream]);

  const changeSource = useCallback(
    async (sourceId: string): Promise<void> => {
      dispatch({ type: "source_busy", busy: true });
      try {
        const record = await api.getSource(sourceId);
        dispatch({ type: "batch", batch: record });
        dispatch({ type: "current_source", source: record });
        dispatch({ type: "stream", stream: await api.sourceStart(sourceId) });
        await refreshSources();
      } catch (error) {
        dispatch({ type: "batch_error", error: toApiError(error) });
      }
    },
    [refreshSources],
  );

  const deleteSource = useCallback(
    async (sourceId: string): Promise<void> => {
      try {
        await api.deleteSource(sourceId);
        await refreshSources();
        await refreshStream();
      } catch (error) {
        dispatch({ type: "batch_error", error: toApiError(error) });
      }
    },
    [refreshSources, refreshStream],
  );

  const startStream = useCallback(async () => {
    if (!state.currentSource) {
      dispatch({
        type: "stream_error",
        error: {
          error: true,
          code: "NO_INSPECTION_SOURCE",
          message: "No inspection source selected.",
          detail: "Add an image, image set, or dataset to begin.",
        },
      });
      return;
    }
    dispatch({ type: "stream_busy", busy: true });
    try {
      const status = await api.sourceStart(state.currentSource.source_id);
      dispatch({ type: "stream", stream: status });
    } catch (error) {
      dispatch({ type: "stream_error", error: toApiError(error) });
    }
  }, [state.currentSource]);

  const pauseStream = useCallback(async () => {
    try {
      const status = await api.streamPause();
      dispatch({ type: "stream", stream: status });
    } catch (error) {
      dispatch({ type: "stream_error", error: toApiError(error) });
    }
  }, []);

  const resetStream = useCallback(async () => {
    if (!state.currentSource) return;
    try {
      const status = await api.sourceReset(state.currentSource.source_id);
      dispatch({ type: "stream", stream: status });
    } catch (error) {
      dispatch({ type: "stream_error", error: toApiError(error) });
    }
  }, [state.currentSource]);

  const setStreamSpeed = useCallback(async (speed: number) => {
    try {
      const status = await api.streamSpeed(speed);
      dispatch({ type: "stream", stream: status });
    } catch (error) {
      dispatch({ type: "stream_error", error: toApiError(error) });
    }
  }, []);

  const runInvestigationFor = useCallback(
    async (inspectionId: string): Promise<InvestigationRecord | null> => {
      dispatch({ type: "investigating", investigating: true });
      try {
        const record = await api.runInvestigation(inspectionId, state.datasetId);
        dispatch({ type: "investigation", investigation: record });
        const list = await api.listInvestigations();
        dispatch({ type: "investigations", investigations: list.investigations });
        return record;
      } catch (error) {
        dispatch({ type: "stream_error", error: toApiError(error) });
        dispatch({ type: "investigating", investigating: false });
        return null;
      }
    },
    [state.datasetId],
  );

  const refreshInvestigations = useCallback(async () => {
    try {
      const list = await api.listInvestigations();
      dispatch({ type: "investigations", investigations: list.investigations });
    } catch {
      /* backend offline */
    }
  }, []);

  const loadInvestigation = useCallback(async (investigationId: string): Promise<InvestigationRecord | null> => {
    try {
      const record = await api.getInvestigation(investigationId);
      dispatch({ type: "investigation", investigation: record });
      return record;
    } catch (error) {
      dispatch({ type: "stream_error", error: toApiError(error) });
      return null;
    }
  }, []);

  const refreshFeatureSpace = useCallback(async () => {
    try {
      const payload = await api.getFeatureSpace();
      dispatch({ type: "feature_space", featureSpace: payload });
    } catch {
      /* backend offline */
    }
  }, []);

  const refreshTimeline = useCallback(async () => {
    if (!state.datasetId) return;
    dispatch({ type: "timeline_busy", busy: true });
    try {
      const payload = await api.getProcessTimeline(state.datasetId);
      dispatch({ type: "timeline", timeline: payload });
    } catch (error) {
      dispatch({ type: "stream_error", error: toApiError(error) });
      dispatch({ type: "timeline", timeline: null });
    }
  }, [state.datasetId]);

  // ------------------------------------------------------------------
  // V2.1 batch + review
  // ------------------------------------------------------------------

  const refreshBatches = useCallback(async () => {
    try {
      const list = await api.listBatches();
      dispatch({ type: "batches", batches: list.batches });
    } catch {
      /* backend offline */
    }
  }, []);

  const createBatch = useCallback(
    async (files: File[]): Promise<BatchRecord | null> => {
      dispatch({ type: "batch_busy", busy: true });
      try {
        const record = await api.createBatch(files);
        dispatch({ type: "batch", batch: record });
        await refreshBatches();
        return record;
      } catch (error) {
        dispatch({ type: "batch_error", error: toApiError(error) });
        return null;
      }
    },
    [refreshBatches],
  );

  const inspectBatch = useCallback(async (batchId: string) => {
    try {
      const sourceId = state.batch && "source_id" in state.batch ? (state.batch as InspectionSource).source_id : null;
      const record = sourceId ? await api.sourceInspect(sourceId) : await api.inspectBatch(batchId);
      dispatch({ type: "batch", batch: record });
      await refreshStream();
    } catch (error) {
      dispatch({ type: "batch_error", error: toApiError(error) });
    }
  }, [state.batch, refreshStream]);

  const refreshBatch = useCallback(
    async (batchId: string): Promise<BatchRecord | null> => {
      try {
        const sourceId = state.batch && "source_id" in state.batch ? (state.batch as InspectionSource).source_id : null;
        const record = sourceId ? await api.getSource(sourceId) : await api.getBatch(batchId);
        dispatch({ type: "batch", batch: record });
        return record;
      } catch (error) {
        dispatch({ type: "batch_error", error: toApiError(error) });
        return null;
      }
    },
    [state.batch],
  );

  const resetBatch = useCallback(() => dispatch({ type: "batch", batch: null }), []);

  const refreshReview = useCallback(async () => {
    try {
      const [queue, stats] = await Promise.all([api.getReviewQueue(), api.getReviewStats()]);
      dispatch({ type: "review_queue", queue: queue.items });
      dispatch({ type: "review_stats", stats });
    } catch {
      /* backend offline */
    }
  }, []);

  const reviewAction = useCallback(
    async (inspectionId: string, action: string, note?: string, className?: string) => {
      dispatch({ type: "review_busy", busy: true });
      try {
        const response = await api.reviewAction(inspectionId, action, note, className);
        dispatch({ type: "review_action", response });
        await refreshReview();
      } catch (error) {
        dispatch({ type: "batch_error", error: toApiError(error) });
        dispatch({ type: "review_busy", busy: false });
      }
    },
    [refreshReview],
  );

  /**
   * Process the next real stream frame. When auto-investigation is enabled,
   * actionable decisions (DEFECT / REVIEW) immediately trigger the
   * investigation chain over the stored result.
   */
  const processNextFrame = useCallback(async (): Promise<VisionInspection | null> => {
    if (!state.currentSource) {
      dispatch({
        type: "stream_error",
        error: {
          error: true,
          code: "NO_INSPECTION_SOURCE",
          message: "No inspection source selected.",
          detail: "Add an image, image set, or dataset to begin.",
        },
      });
      return null;
    }
    dispatch({ type: "stream_busy", busy: true });
    try {
      const response = await api.sourceNext(state.currentSource.source_id);
      dispatch({ type: "stream", stream: response.status });
      if (!response.inspection) {
        return null;
      }
      const inspection = response.inspection;
      dispatch({ type: "stream_start", imageUrl: `${API_BASE}/api/vision/inspect/${inspection.inspection_id}/image` });
      for (const stage of inspection.trace) {
        dispatch({ type: "stream_stage", stage });
      }
      dispatch({ type: "inspection", inspection });
      const history = await api.getVisionHistory();
      dispatch({ type: "inspection_history", history: history.inspections });
      void refreshReview();
      if (state.autoInvestigation && (inspection.decision === "DEFECT" || inspection.decision === "REVIEW")) {
        void runInvestigationFor(inspection.inspection_id);
      }
      return inspection;
    } catch (error) {
      dispatch({ type: "stream_error", error: toApiError(error) });
      return null;
    }
  }, [state.autoInvestigation, state.currentSource, runInvestigationFor, refreshReview]);

  const setAutoInvestigation = useCallback((value: boolean) => {
    dispatch({ type: "auto_investigation", enabled: value });
  }, []);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const health = await api.health();
        if (!cancelled) dispatch({ type: "backend", online: health.status === "ok" });
      } catch {
        if (!cancelled) dispatch({ type: "backend", online: false });
      }
    };
    void check();
    const timer = window.setInterval(check, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    api
      .listDatasets()
      .then((result) => dispatch({ type: "datasets", datasets: result.datasets }))
      .catch(() => {
        /* backend may be offline; empty state still renders honestly */
      });
  }, []);

  useEffect(() => {
    void refreshVision();
    void refreshStream();
    void refreshInvestigations();
    void refreshFeatureSpace();
    void refreshBatches();
    void refreshReview();
    void refreshSources();
  }, [refreshVision, refreshStream, refreshInvestigations, refreshFeatureSpace, refreshBatches, refreshReview, refreshSources]);

  const coverage: Coverage | null = state.analysis?.coverage ?? null;

  const value = useMemo<SessionContextValue>(
    () => ({
      ...state,
      apiBase: API_BASE,
      uploadFile,
      loadDataset,
      refreshDatasets,
      runRootCause,
      runBottleneck,
      saveAssumptions,
      refreshBaseline,
      runScenario,
      generateRecommendations,
      refreshRecommendations,
      reset,
      inspectFile,
      refreshVision,
      trainVisionModel,
      loadInspection,
      setCinematic,
      refreshStream,
      startStream,
      pauseStream,
      resetStream,
      setStreamSpeed,
      processNextFrame,
      setAutoInvestigation,
      runInvestigationFor,
      refreshInvestigations,
      loadInvestigation,
      refreshFeatureSpace,
      refreshTimeline,
      createBatch,
      inspectBatch,
      refreshBatch,
      refreshBatches,
      resetBatch,
      refreshReview,
      reviewAction,
      refreshSources,
      createSource,
      createDemoSource,
      changeSource,
      deleteSource,
    }),
    [
      state,
      uploadFile,
      loadDataset,
      refreshDatasets,
      runRootCause,
      runBottleneck,
      saveAssumptions,
      refreshBaseline,
      runScenario,
      generateRecommendations,
      refreshRecommendations,
      reset,
      inspectFile,
      refreshVision,
      trainVisionModel,
      loadInspection,
      setCinematic,
      refreshStream,
      startStream,
      pauseStream,
      resetStream,
      setStreamSpeed,
      processNextFrame,
      setAutoInvestigation,
      runInvestigationFor,
      refreshInvestigations,
      loadInvestigation,
      refreshFeatureSpace,
      refreshTimeline,
      createBatch,
      inspectBatch,
      refreshBatch,
      refreshBatches,
      resetBatch,
      refreshReview,
      reviewAction,
      refreshSources,
      createSource,
      createDemoSource,
      changeSource,
      deleteSource,
    ],
  );

  void coverage;
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider");
  return context;
}
