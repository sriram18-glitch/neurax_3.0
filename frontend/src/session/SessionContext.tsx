/**
 * Dataset session store.
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
  BottleneckAnalysis,
  Coverage,
  DatasetContract,
  DatasetListItem,
  MlSummary,
  RecommendationListResponse,
  RecommendationRun,
  RootCauseAnalysis,
  ScenarioPayload,
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
  | { type: "cinematic"; cinematic: boolean };

function reducer(state: SessionState, action: Action): SessionState {
  switch (action.type) {
    case "reset":
      return { ...initialState, datasets: state.datasets, backendOnline: state.backendOnline };
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
    }
  }, [withBusy, refreshVision]);

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
  }, [refreshVision]);

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
