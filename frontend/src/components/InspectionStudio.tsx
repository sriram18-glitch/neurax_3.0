import { motion, useReducedMotion } from "framer-motion";
import { Database, Eye, EyeOff, FolderOpen, FolderUp, Play, ScanLine, Sparkles, UploadCloud, ZoomIn, ZoomOut } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { API_BASE } from "../api/client";
import { useSession } from "../session/SessionContext";
import type { VisionTraceStage } from "../types/api";
import type { OpenEvidence } from "./evidence";
import { AIInferencePipeline, PIPELINE_NODE_TRACE } from "./neurax/AIInferencePipeline";
import { AnomalyMeter } from "./neurax/AnomalyMeter";
import { AutomationControl } from "./neurax/AutomationControl";
import { AutomationGate } from "./neurax/AutomationGate";
import { BatchPanel } from "./neurax/BatchPanel";
import { InspectionSourceBar } from "./neurax/InspectionSource";
import { ConfidenceRing } from "./neurax/ConfidenceRing";
import { DecisionChain, type ChainStep, type ChainStepId } from "./neurax/DecisionChain";
import { DecisionQuality } from "./neurax/DecisionQuality";
import { DecisionState, type Decision } from "./neurax/DecisionState";
import { DecisionTrace } from "./neurax/DecisionTrace";
import { EvidenceBadge } from "./neurax/EvidenceBadge";
import { EvidenceGraph } from "./neurax/EvidenceGraph";
import { FeatureSpaceMap } from "./neurax/FeatureSpaceMap";
import { HudPanel, MotionSection } from "./neurax/Motion";
import { NoveltyGauge } from "./neurax/NoveltyGauge";
import { ProbabilityBars } from "./neurax/ProbabilityBars";
import { ProductionStream } from "./neurax/ProductionStream";
import { inspectionGraph, inspectionTraceSteps, STAGE_ORDER } from "./neurax/adapt";

type InputMode = "auto" | "imageset" | "folder" | "single" | "source";

const DECISION_TONE: Record<string, { border: string; text: string; bg: string }> = {
  PASS: { border: "border-ok", text: "text-ok", bg: "bg-ok/10" },
  DEFECT: { border: "border-bad", text: "text-bad", bg: "bg-bad/10" },
  REVIEW: { border: "border-warn", text: "text-warn", bg: "bg-warn/10" },
};

/** 02 — the inspection experience: stream-first, manual and batch are fallbacks. */
export function InspectionStudio({
  onOpenEvidence,
  onGoAnalysis,
  modeRequest,
  onAddData,
}: {
  onOpenEvidence: OpenEvidence;
  onGoAnalysis: () => void;
  modeRequest?: { mode?: InputMode } | null;
  onAddData: () => void;
}) {
  const {
    visionStatus,
    inspection,
    inspecting,
    inspectFile,
    trainVisionModel,
    busy,
    liveStages,
    liveStatus,
    liveImageUrl,
    cinematic,
    setCinematic,
    datasets,
    loadDataset,
    datasetId,
    refreshTimeline,
  } = useSession();

  const [mode, setMode] = useState<InputMode>("auto");
  useEffect(() => {
    if (modeRequest?.mode) setMode(modeRequest.mode);
  }, [modeRequest]);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [replayCount, setReplayCount] = useState<number | null>(null);
  const [activeSection, setActiveSection] = useState<ChainStepId | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const reduceMotion = useReducedMotion();

  const streaming = liveStatus === "streaming";
  const stages: VisionTraceStage[] = useMemo(() => {
    if (replayCount !== null && inspection) return inspection.trace.slice(0, replayCount);
    return liveStages.length > 0 ? liveStages : (inspection?.trace ?? []);
  }, [replayCount, inspection, liveStages]);

  const activeStageId = useMemo(() => {
    if (replayCount !== null) return null;
    if (!streaming) return null;
    const completed = new Set(stages.map((stage) => stage.id));
    return STAGE_ORDER.find((id) => !completed.has(id)) ?? null;
  }, [streaming, stages, replayCount]);

  useEffect(() => {
    if (replayCount === null || !inspection) return;
    if (replayCount >= inspection.trace.length) return;
    const timer = window.setTimeout(() => setReplayCount((count) => (count ?? 0) + 1), reduceMotion ? 60 : 450);
    return () => window.clearTimeout(timer);
  }, [replayCount, inspection, reduceMotion]);

  const handleFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0];
      if (file) {
        setMode("single");
        setReplayCount(null);
        void inspectFile(file);
      }
    },
    [inspectFile],
  );

  useEffect(() => {
    const node = viewportRef.current;
    if (!node) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      setZoom((current) => Math.min(4, Math.max(1, current * (event.deltaY < 0 ? 1.12 : 0.89))));
    };
    node.addEventListener("wheel", onWheel, { passive: false });
    return () => node.removeEventListener("wheel", onWheel);
  }, [inspection?.inspection_id]);

  useEffect(() => {
    setZoom(1);
  }, [inspection?.inspection_id]);

  const openTechnical = useCallback(
    (nodeId: string) => {
      if (!inspection) return;
      const traceIds = PIPELINE_NODE_TRACE[nodeId] ?? [];
      const items = traceIds
        .map((id) => inspection.trace.find((stage) => stage.id === id))
        .filter(Boolean)
        .flatMap((stage) => {
          const entries = Object.entries(stage?.metrics ?? {}).filter(([key]) => !["preprocessed_png_base64", "heatmap_png_base64", "embedding"].includes(key));
          return entries.map(([key, value]) => ({
            statement: `${stage?.id.replace(/_/g, " ")} · ${key.replace(/_/g, " ")}`,
            detail: typeof value === "object" && value !== null ? JSON.stringify(value) : String(value),
            source_artifact: `vision/inspect/${inspection.inspection_id}/trace`,
            epistemic_status: stage?.status === "not_supported" ? "NOT_AVAILABLE" : "MODEL_OUTPUT",
          }));
        });
      onOpenEvidence(
        `Technical evidence — ${nodeId}`,
        `${inspection.inspection_id} · observable outputs only (no chain-of-thought)`,
        items,
        inspection.limitations,
      );
    },
    [inspection, onOpenEvidence],
  );

  const chainSteps: ChainStep[] = useMemo(() => {
    const confidence = inspection?.confidence.value ?? null;
    return [
      {
        id: "what",
        label: "WHAT",
        question: "what is wrong?",
        status: inspection ? "complete" : "waiting",
        detail: inspection ? `${inspection.prediction.predicted_class} — ${inspection.decision}` : "no inspection yet",
        result: inspection ? `${inspection.prediction.predicted_class} · ${inspection.decision}` : "—",
        source: inspection ? "vision model output" : null,
      },
      {
        id: "where",
        label: "WHERE",
        question: "where is it?",
        status: inspection?.localization.bounding_box ? "complete" : inspection ? "partial" : "waiting",
        detail: inspection?.localization.bounding_box
          ? "model-derived attention region (ground truth not available)"
          : inspection
            ? "no attention region produced"
            : "—",
        result: inspection?.localization.bounding_box ? "MODEL-DERIVED REGION" : inspection ? "no region" : "—",
        source: inspection ? "class-activation map" : null,
      },
      {
        id: "certain",
        label: "HOW CERTAIN",
        question: "how certain is the system?",
        status: inspection ? "complete" : "waiting",
        detail: inspection
          ? `calibrated ${((confidence ?? 0) * 100).toFixed(1)}% · novelty ${inspection.anomaly_score.novelty_status}`
          : "—",
        result: inspection ? `${((confidence ?? 0) * 100).toFixed(1)}% CALIBRATED` : "—",
        source: inspection ? "temperature-scaled softmax" : null,
      },
      {
        id: "why",
        label: "WHY",
        question: "why does the system believe this?",
        status: inspection ? "complete" : "waiting",
        detail: inspection ? `${inspection.evidence.length} recorded evidence statement(s)` : "—",
        result: inspection ? `${inspection.evidence.length} evidence items` : "—",
        source: inspection ? "evidence records" : null,
      },
      {
        id: "flow",
        label: "FLOW",
        question: "where is the production constraint?",
        status: "partial",
        detail: "dataset-level process analysis lives in Process Intelligence",
        result: "DATA GAP — process dataset required",
        source: "process analysis engine",
      },
      {
        id: "impact",
        label: "IMPACT",
        question: "what is the impact?",
        status: "partial",
        detail: "assumption-based economic model",
        result: "ASSUMPTIONS REQUIRED",
        source: "economic model",
      },
      {
        id: "next",
        label: "WHAT NEXT",
        question: "what should be investigated?",
        status: "partial",
        detail: "advisory actions from deterministic rules",
        result: "WAITING FOR PROCESS EVIDENCE",
        source: "recommendation engine",
      },
    ];
  }, [inspection]);

  if (!visionStatus) {
    return (
      <div className="flex h-full items-center justify-center px-6">
        <p className="text-xs text-ink-3">Connecting to the vision service…</p>
      </div>
    );
  }

  if (!visionStatus.model_available) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4 px-6 py-14">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center border border-line">
            <ScanLine size={18} className="text-ink-3" aria-hidden />
          </div>
          <h1 className="text-xl font-semibold tracking-tight text-ink">Visual inspection model not trained</h1>
          <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-ink-2">
            {visionStatus.dataset_available
              ? "An image dataset was found. Train the inspection model to enable the automated inspection stream."
              : visionStatus.reason}
          </p>
        </div>
        <div className="hud px-5 py-4">
          <p className="label mb-2">Requirements</p>
          <p className="text-xs text-ink-2">{visionStatus.requirements?.needs}</p>
          <p className="mt-1 font-mono text-2xs text-cyan">{visionStatus.requirements?.minimum}</p>
          <p className="mt-3 font-mono text-2xs text-ink-3">{visionStatus.dataset_dir}</p>
        </div>
        {visionStatus.dataset_available && (
          <button type="button" className="btn-primary mx-auto" onClick={() => void trainVisionModel()} disabled={Boolean(busy)}>
            <Sparkles size={13} aria-hidden />
            {busy ?? "Train vision model"}
          </button>
        )}
      </div>
    );
  }

  const imageUrl = liveImageUrl ?? (inspection ? `${API_BASE}/api/vision/inspect/${inspection.inspection_id}/image` : null);
  const decision = (inspection?.decision ?? null) as Decision | null;
  const graph = inspection ? inspectionGraph(inspection) : null;
  const preprocessed = inspection?.preprocessing.preprocessed_png_base64;

  return (
    <div
      className="flex flex-col gap-3 p-3"
      onDragOver={(event) => {
        event.preventDefault();
      }}
      onDrop={(event) => {
        event.preventDefault();
        handleFiles(event.dataTransfer.files);
      }}
    >
      {/* input mode switch — automation first */}
      <div className="flex flex-wrap items-center justify-between gap-3 border border-line/60 bg-panel/60 px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Inspection input mode">
          {(
            [
              { id: "auto", label: "AUTO PRODUCTION STREAM", icon: Play },
              { id: "imageset", label: "IMAGE SET", icon: FolderUp },
              { id: "folder", label: "FOLDER DATASET", icon: FolderOpen },
              { id: "single", label: "SINGLE IMAGE", icon: UploadCloud },
              { id: "source", label: "CONNECT DATA SOURCE", icon: Database },
            ] as const
          ).map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setMode(id)}
              aria-pressed={mode === id}
              className={`chip ${mode === id ? "border-cyan/50 bg-cyan/10 text-cyan" : "border-line text-ink-3 hover:text-ink-2"}`}
            >
              <Icon size={10} aria-hidden />
              {label}
            </button>
          ))}
        </div>
        {mode === "auto" && <AutomationControl compact />}
        {mode === "single" && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="btn-ghost !px-2 !py-1"
              onClick={() => setCinematic(!cinematic)}
              aria-pressed={cinematic}
              title="Cinematic pacing holds each completed stage briefly so it can be read."
            >
              {cinematic ? <Eye size={11} aria-hidden /> : <EyeOff size={11} aria-hidden />}
              {cinematic ? "Cinematic" : "Raw speed"}
            </button>
            <button type="button" className="btn-primary !px-2.5 !py-1.5" onClick={() => inputRef.current?.click()} disabled={inspecting}>
              <UploadCloud size={11} aria-hidden />
              {inspecting ? "Analyzing…" : "Upload image"}
            </button>
          </div>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        accept=".png,.jpg,.jpeg,.bmp,.tif,.tiff,.webp"
        onChange={(event) => handleFiles(event.target.files)}
        aria-label="Upload inspection image"
      />

      {mode === "imageset" && (
        <MotionSection>
          <BatchPanel mode="image-set" />
        </MotionSection>
      )}

      {mode === "folder" && (
        <MotionSection>
          <BatchPanel mode="folder" />
        </MotionSection>
      )}

      {mode === "source" && (
        <MotionSection>
          <HudPanel title="Connect data source" subtitle="stored process datasets on this backend">
            <div className="flex flex-col gap-2 px-4 py-3">
              <p className="text-2xs leading-relaxed text-ink-3">
                Vision inspection runs without process data. Connecting a process dataset enables dataset-level
                root-cause, flow, impact and recommendation stages in the investigation chain.
              </p>
              {datasets.length === 0 ? (
                <p className="text-2xs text-ink-3">No processed datasets stored yet.</p>
              ) : (
                <ul className="grid gap-px bg-line/40 sm:grid-cols-2">
                  {datasets.map((dataset) => (
                    <li key={dataset.dataset_id}>
                      <button
                        type="button"
                        onClick={() => {
                          void loadDataset(dataset.dataset_id);
                          void refreshTimeline();
                          onGoAnalysis();
                        }}
                        className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition-colors hover:bg-panel-2/60 ${
                          dataset.dataset_id === datasetId ? "bg-cyan/5 text-cyan" : "bg-panel/70 text-ink-2"
                        }`}
                      >
                        <span className="truncate text-2xs">{dataset.filename ?? dataset.dataset_id}</span>
                        <span className="shrink-0 font-mono text-[9px] text-ink-3">
                          {dataset.rows !== null ? `${dataset.rows.toLocaleString()} rows` : dataset.status}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </HudPanel>
        </MotionSection>
      )}

      {mode === "single" && !inspection && (
        <MotionSection>
          <HudPanel title="Manual inspection" subtitle="fallback mode — the automated stream is the primary experience">
            <div className="flex flex-col items-center gap-3 px-4 py-12 text-center">
              <ScanLine size={24} className="text-ink-3" aria-hidden />
              <p className="text-sm text-ink-2">Drop an inspection image — the real pipeline runs live</p>
              <p className="max-w-md text-2xs leading-relaxed text-ink-3">
                The same pipeline that powers the automated stream: validation, preprocessing, backbone embedding,
                calibrated classification, anomaly analysis, localization and the PASS/DEFECT/REVIEW decision.
              </p>
            </div>
          </HudPanel>
        </MotionSection>
      )}

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-3">
          {mode === "auto" && (
            <HudPanel title="Inspection source" subtitle="selected at runtime — never a hardcoded dataset path">
              <InspectionSourceBar onAddData={onAddData} />
            </HudPanel>
          )}

          {mode === "auto" && (
            <HudPanel title="Production stream" subtitle="simulated production stream — real frames from the selected source">
              <ProductionStream />
            </HudPanel>
          )}

          <HudPanel
            title="Inspection"
            subtitle={inspection?.filename ?? "waiting for a frame"}
            actions={
              <div className="flex items-center gap-2">
                {streaming && (
                  <span className="chip border-cyan/50 bg-cyan/10 text-cyan">
                    <span className="h-1.5 w-1.5 animate-pulse bg-cyan" aria-hidden />
                    LIVE
                  </span>
                )}
                {!streaming && decision && (
                  <span className={`chip ${DECISION_TONE[decision]?.border ?? "border-line-2"} ${DECISION_TONE[decision]?.text ?? "text-ink-2"}`}>
                    {decision}
                  </span>
                )}
                <button
                  type="button"
                  className="btn-ghost !px-2 !py-1"
                  onClick={() => inspection && setReplayCount(0)}
                  disabled={!inspection || inspecting}
                  title="Replays the stored stage trace of this inspection (display only)."
                >
                  <Play size={11} aria-hidden />
                  Replay decision
                </button>
              </div>
            }
          >
            <div ref={viewportRef} className="grid-floor relative flex min-h-[380px] items-center justify-center overflow-hidden bg-black/50 p-4">
              {imageUrl ? (
                <div className="relative inline-block" style={{ transform: `scale(${zoom})`, transformOrigin: "center" }}>
                  <img
                    src={imageUrl}
                    alt="Inspected unit"
                    className="h-[38vh] min-h-[220px] w-auto border border-line-2"
                    draggable={false}
                  />
                  {showHeatmap && inspection?.localization.heatmap_png_base64 && !streaming && (
                    <img
                      src={`data:image/png;base64,${inspection.localization.heatmap_png_base64}`}
                      alt="Model anomaly heatmap"
                      className="pointer-events-none absolute inset-0 h-full w-full opacity-60 mix-blend-screen"
                    />
                  )}
                  {inspection?.localization.bounding_box && !streaming && (
                    <motion.div
                      className="pointer-events-none absolute border-2 border-cyan"
                      style={{
                        left: `${(inspection.localization.bounding_box.x / inspection.image_metadata.width) * 100}%`,
                        top: `${(inspection.localization.bounding_box.y / inspection.image_metadata.height) * 100}%`,
                        width: `${(inspection.localization.bounding_box.width / inspection.image_metadata.width) * 100}%`,
                        height: `${(inspection.localization.bounding_box.height / inspection.image_metadata.height) * 100}%`,
                      }}
                      initial={reduceMotion ? false : { opacity: 0, scale: 1.2 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ duration: 0.4 }}
                    >
                      <span className="absolute -top-5 left-0 whitespace-nowrap bg-cyan/20 px-1 font-mono text-2xs text-cyan">
                        MODEL-DERIVED REGION
                      </span>
                    </motion.div>
                  )}
                  {streaming && !reduceMotion && (
                    <motion.div
                      className="pointer-events-none absolute inset-x-0 h-14 bg-gradient-to-b from-transparent via-cyan/25 to-transparent"
                      initial={{ top: "-15%" }}
                      animate={{ top: ["-15%", "105%"] }}
                      transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
                    />
                  )}
                  {!streaming && decision && (
                    <motion.span
                      key={decision}
                      initial={reduceMotion ? false : { opacity: 0, scale: 1.7, rotate: -12 }}
                      animate={{ opacity: 1, scale: 1, rotate: -7 }}
                      transition={{ type: "spring", stiffness: 320, damping: 18 }}
                      className={`absolute right-3 top-3 border-4 px-3 py-1.5 font-mono text-lg font-bold tracking-[0.16em] ${DECISION_TONE[decision]?.border} ${DECISION_TONE[decision]?.bg} backdrop-blur`}
                    >
                      <span className={DECISION_TONE[decision]?.text}>{decision}</span>
                    </motion.span>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2 py-14 text-center">
                  <ScanLine size={24} className="text-ink-3" aria-hidden />
                  <p className="text-sm text-ink-2">
                    {mode === "auto" ? "Start the automated inspection stream" : "Waiting for an image"}
                  </p>
                  <p className="max-w-md text-2xs leading-relaxed text-ink-3">
                    {mode === "auto"
                      ? "Real frames flow from the dataset through the trained pipeline; every actionable decision triggers an investigation."
                      : "Switch to AUTO PRODUCTION STREAM for the primary experience, or upload a single image in manual mode."}
                  </p>
                </div>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line/60 px-4 py-2">
              <div className="flex items-center gap-1">
                <button type="button" className="btn-ghost !px-1.5 !py-0.5" onClick={() => setZoom((value) => Math.min(4, value * 1.2))} aria-label="Zoom in">
                  <ZoomIn size={11} aria-hidden />
                </button>
                <button type="button" className="btn-ghost !px-1.5 !py-0.5" onClick={() => setZoom((value) => Math.max(1, value / 1.2))} aria-label="Zoom out">
                  <ZoomOut size={11} aria-hidden />
                </button>
                <span className="font-mono text-2xs text-ink-3">{zoom.toFixed(1)}×</span>
              </div>
              <button type="button" className="text-2xs text-ink-3 hover:text-ink-2" onClick={() => setShowHeatmap((value) => !value)}>
                heatmap {showHeatmap ? "on" : "off"}
              </button>
              {inspection && (
                <span className="font-mono text-2xs text-ink-3">
                  {inspection.image_metadata.width} × {inspection.image_metadata.height} · {inspection.image_metadata.format}
                </span>
              )}
              <span className="font-mono text-2xs text-novel">
                LOCALIZATION: MODEL-DERIVED · ground truth: NOT AVAILABLE
              </span>
              {mode === "single" && preprocessed && (
                <span className="font-mono text-2xs text-ink-3">preprocessed tensor recorded</span>
              )}
            </div>
          </HudPanel>

          <HudPanel
            title="AI inference pipeline"
            subtitle={streaming ? "live from the backend" : "recorded trace of this inspection"}
            actions={
              <button
                type="button"
                className="btn-ghost !px-2 !py-1"
                onClick={() => {
                  if (!inspection) return;
                  onOpenEvidence(
                    "Decision trace",
                    `${inspection.inspection_id} · ${inspection.generated_at}`,
                    inspectionTraceSteps(inspection).map((step) => ({
                      statement: step.label,
                      detail: step.detail,
                      source_artifact: `vision/inspect/${inspection.inspection_id}`,
                      epistemic_status: step.epistemic.replace(/ /g, "_"),
                    })),
                    inspection.limitations,
                  );
                }}
                disabled={!inspection}
              >
                Decision trace
              </button>
            }
          >
            <AIInferencePipeline
              inspection={inspection}
              liveStages={stages}
              streaming={streaming}
              activeStageId={activeStageId}
              onTechnical={openTechnical}
            />
          </HudPanel>

          <HudPanel title="Feature space" subtitle="real embedding projection (PCA of training data)">
            <FeatureSpaceMap />
          </HudPanel>

          {graph && inspection && (
            <HudPanel title="Evidence graph" subtitle="every node is real output from this inspection">
              <EvidenceGraph nodes={graph.nodes} edges={graph.edges} />
            </HudPanel>
          )}
        </div>

        <div className="flex min-w-0 flex-col gap-3">
          <HudPanel title="Decision" subtitle={inspection ? `inspection ${inspection.inspection_id}` : "threshold rules on calibrated output"}>
            <DecisionState decision={decision} reason={inspection?.review_reason ?? null} confidence={inspection?.confidence.value ?? null} thresholds={visionStatus.thresholds} />
            <div className="border-t border-line/60 px-4 py-3">
              <AutomationGate
                decision={decision}
                confidence={inspection?.confidence.value ?? null}
                noveltyScore={inspection?.anomaly_score.novelty_score}
                noveltyStatus={inspection?.anomaly_score.novelty_status}
              />
            </div>
          </HudPanel>

          <HudPanel title="Classification" subtitle="calibrated class probabilities">
            <div className="flex flex-col items-center gap-3 px-4 py-3">
              <ConfidenceRing value={inspection?.confidence.value ?? null} level={inspection?.confidence.level} method={inspection?.confidence.method} />
              <div className="w-full min-w-0">
                <ProbabilityBars probabilities={inspection?.class_probabilities} winner={inspection?.prediction.predicted_class} />
              </div>
            </div>
          </HudPanel>

          <HudPanel title="Robustness" subtitle="novelty vs the known distribution">
            <NoveltyGauge
              noveltyScore={inspection?.anomaly_score.novelty_score}
              noveltyStatus={inspection?.anomaly_score.novelty_status}
              anomalyScore={inspection?.anomaly_score.value}
              decision={inspection?.decision}
              gate={visionStatus.thresholds?.anomaly_review_percentile}
            />
          </HudPanel>

          <HudPanel title="Anomaly" subtitle="percentile against the normal reference">
            <AnomalyMeter
              anomalyScore={inspection?.anomaly_score.value}
              noveltyScore={inspection?.anomaly_score.novelty_score}
              noveltyStatus={inspection?.anomaly_score.novelty_status}
              gate={visionStatus.thresholds?.anomaly_review_percentile}
            />
          </HudPanel>

          <HudPanel title="Decision quality" subtitle="measured on the held-out test split">
            <DecisionQuality />
          </HudPanel>

          <HudPanel
            title="Evidence"
            subtitle="statements recorded with this inspection"
            actions={
              <button
                type="button"
                className="btn-ghost !px-2 !py-1"
                onClick={() => {
                  if (!inspection) return;
                  onOpenEvidence(
                    `Why ${inspection.decision}?`,
                    `${inspection.prediction.predicted_class} · calibrated confidence ${(inspection.confidence.value * 100).toFixed(1)}%`,
                    inspection.evidence.map((entry) => ({
                      statement: entry.statement,
                      detail: `source: ${entry.source}`,
                      source_artifact: `vision/${entry.source}`,
                      epistemic_status: entry.epistemic_status,
                    })),
                    inspection.limitations,
                  );
                }}
                disabled={!inspection}
              >
                WHY?
              </button>
            }
          >
            {inspection ? (
              <div className="flex flex-col gap-2 px-4 py-3">
                {inspection.evidence.map((entry, index) => (
                  <div key={index} className="border-b border-line/40 pb-2 last:border-b-0 last:pb-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <EvidenceBadge status={entry.epistemic_status.replace(/_/g, " ")} />
                      <span className="text-2xs text-ink-3">source: {entry.source}</span>
                    </div>
                    <p className="mt-1 text-2xs leading-relaxed text-ink-2">{entry.statement}</p>
                  </div>
                ))}
                <p className="text-2xs leading-relaxed text-ink-3">{inspection.process_link.reason}</p>
              </div>
            ) : (
              <p className="px-4 py-3 text-2xs text-ink-3">No inspection yet.</p>
            )}
          </HudPanel>

          {inspection && (
            <HudPanel title="Decision trace" subtitle="data lineage of this decision">
              <DecisionTrace steps={inspectionTraceSteps(inspection).slice(0, 8)} />
            </HudPanel>
          )}
        </div>
      </div>

      <MotionSection delay={0.1}>
        <HudPanel title="Decision chain" subtitle="what → where → how certain → why → flow → impact → what next">
          <DecisionChain
            steps={chainSteps}
            onSelect={(id) => {
              setActiveSection(id);
              if (id === "flow" || id === "impact" || id === "next") onGoAnalysis();
            }}
          />
          {activeSection && (
            <p className="border-t border-line/60 px-4 py-2 text-2xs text-ink-3">
              FLOW, IMPACT and WHAT NEXT build on the process dataset — open Process Intelligence for the full chain.
            </p>
          )}
        </HudPanel>
      </MotionSection>
    </div>
  );
}
