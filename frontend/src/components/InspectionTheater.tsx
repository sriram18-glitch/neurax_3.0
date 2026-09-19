import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  Crosshair,
  Eye,
  EyeOff,
  Gauge,
  ScanLine,
  Sparkles,
  UploadCloud,
  Zap,
} from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";

import { API_BASE } from "../api/client";
import { useSession } from "../session/SessionContext";
import type { VisionInspection, VisionTraceStage } from "../types/api";
import type { OpenEvidence } from "./evidence";
import { Panel, formatNumber, statusIcon, statusTone } from "./ui/Primitives";

const STAGE_ORDER = [
  "image_received",
  "validation",
  "preprocessing",
  "feature_extraction",
  "classification",
  "anomaly_analysis",
  "localization",
  "confidence",
  "decision",
  "process_link",
];

const DECISION_STYLE: Record<string, { border: string; text: string; bg: string }> = {
  PASS: { border: "border-ok", text: "text-ok", bg: "bg-ok/10" },
  DEFECT: { border: "border-bad", text: "text-bad", bg: "bg-bad/10" },
  REVIEW: { border: "border-warn", text: "text-warn", bg: "bg-warn/10" },
};

export function InspectionTheater({ onOpenEvidence }: { onOpenEvidence: OpenEvidence }) {
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
  } = useSession();
  const [dragging, setDragging] = useState(false);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [showBox, setShowBox] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);
  const reduceMotion = useReducedMotion();

  const handleFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0];
      if (file) void inspectFile(file);
    },
    [inspectFile],
  );

  const byId = useMemo(() => {
    const map = new Map<string, VisionTraceStage>();
    for (const stage of liveStages) map.set(stage.id, stage);
    return map;
  }, [liveStages]);

  const completedIds = liveStages.map((stage) => stage.id);
  const currentStageId = STAGE_ORDER.find((id) => !completedIds.includes(id)) ?? null;

  const preprocessed = (byId.get("preprocessing")?.metrics.preprocessed_png_base64 as string | undefined) ??
    inspection?.preprocessing.preprocessed_png_base64;
  const heatmap = (byId.get("localization")?.metrics.heatmap_png_base64 as string | undefined) ??
    inspection?.localization.heatmap_png_base64;
  const box = (byId.get("localization")?.metrics.bounding_box as VisionInspection["localization"]["bounding_box"]) ??
    inspection?.localization.bounding_box;
  const probabilities = (byId.get("classification")?.metrics.class_probabilities as Record<string, number> | undefined) ??
    inspection?.class_probabilities;
  const anomalyScore = (byId.get("anomaly_analysis")?.metrics.anomaly_score as number | undefined) ??
    inspection?.anomaly_score.value;
  const noveltyScore = (byId.get("anomaly_analysis")?.metrics.novelty_score as number | undefined) ??
    inspection?.anomaly_score.novelty_score;
  const noveltyStatus = (byId.get("anomaly_analysis")?.metrics.novelty_status as string | undefined) ??
    inspection?.anomaly_score.novelty_status;
  const decision = (byId.get("decision")?.metrics.decision as string | undefined) ?? inspection?.decision;
  const reviewReason = (byId.get("decision")?.metrics.review_reason as string | null | undefined) ?? inspection?.review_reason;
  const confidence = (byId.get("confidence")?.metrics.calibrated_probability as number | undefined) ??
    inspection?.confidence.value;
  const confidenceLevel = (byId.get("confidence")?.metrics.confidence_level as string | undefined) ??
    inspection?.confidence.level;

  const imageUrl = liveImageUrl ?? (inspection ? `${API_BASE}/api/vision/inspect/${inspection.inspection_id}/image` : null);
  const width = inspection?.image_metadata.width ?? 256;
  const height = inspection?.image_metadata.height ?? 256;
  const localizationDone = completedIds.includes("localization");
  const scanning = liveStatus === "streaming" && !localizationDone;

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
              ? "An image dataset was found. Train the inspection model to enable the live inspection theater."
              : visionStatus.reason}
          </p>
        </div>
        <div className="panel px-5 py-4">
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

  return (
    <div className="flex flex-col gap-3 p-3">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          handleFiles(event.dataTransfer.files);
        }}
        className={`grid gap-3 xl:grid-cols-[1fr_320px] ${dragging ? "rounded-sm ring-1 ring-cyan/50" : ""}`}
      >
        {/* ---------------- image theater ---------------- */}
        <Panel
          title="Visual inspection"
          subtitle={inspection?.filename ?? "Drop an image to begin"}
          actions={
            <div className="flex items-center gap-2">
              {liveStatus === "streaming" && (
                <span className="chip border-cyan/50 bg-cyan/10 text-cyan">
                  <span className="h-1.5 w-1.5 animate-pulse bg-cyan" aria-hidden />
                  LIVE
                </span>
              )}
              {liveStatus === "complete" && decision && (
                <span className={`chip ${statusTone(decision)}`}>
                  {statusIcon(decision)}
                  {decision}
                </span>
              )}
              <button
                type="button"
                className="btn-ghost !px-2 !py-1"
                onClick={() => setCinematic(!cinematic)}
                aria-pressed={cinematic}
                title="Cinematic pacing holds each completed stage briefly so it can be read. Stage results are real either way."
              >
                {cinematic ? <Eye size={11} aria-hidden /> : <EyeOff size={11} aria-hidden />}
                {cinematic ? "Cinematic" : "Raw speed"}
              </button>
              <button type="button" className="btn-ghost !px-2 !py-1" onClick={() => inputRef.current?.click()} disabled={inspecting}>
                <UploadCloud size={11} aria-hidden />
                {inspecting ? "Analyzing…" : inspection ? "New image" : "Upload image"}
              </button>
            </div>
          }
        >
          <div className="relative flex min-h-[440px] items-center justify-center overflow-hidden bg-black/40 p-4">
            {imageUrl ? (
              <div className="relative inline-block">
                <motion.img
                  key={imageUrl}
                  src={imageUrl}
                  alt="Inspected unit"
                  className="max-h-[54vh] w-auto border border-line-2"
                  initial={reduceMotion ? false : { opacity: 0, scale: 0.98 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.4 }}
                />

                {/* preprocessed flip card */}
                <AnimatePresence>
                  {preprocessed && (
                    <motion.figure
                      initial={reduceMotion ? false : { opacity: 0, x: -8, rotateY: 90 }}
                      animate={{ opacity: 1, x: 0, rotateY: 0 }}
                      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                      className="absolute -left-3 top-3 hidden w-24 border border-cyan/40 bg-bg/90 p-1.5 sm:block"
                    >
                      <img src={`data:image/png;base64,${preprocessed}`} alt="Preprocessed 224x224 tensor" className="w-full" />
                      <figcaption className="mt-1 font-mono text-[9px] text-cyan">224×224 TENSOR</figcaption>
                    </motion.figure>
                  )}
                </AnimatePresence>

                {/* heatmap fade-in */}
                <AnimatePresence>
                  {localizationDone && heatmap && showHeatmap && (
                    <motion.img
                      src={`data:image/png;base64,${heatmap}`}
                      alt="Model anomaly heatmap"
                      className="pointer-events-none absolute inset-0 h-full w-full opacity-70 mix-blend-screen"
                      initial={reduceMotion ? false : { opacity: 0 }}
                      animate={{ opacity: 0.7 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.7 }}
                    />
                  )}
                </AnimatePresence>

                {/* region box */}
                <AnimatePresence>
                  {localizationDone && box && showBox && (
                    <motion.div
                      className="pointer-events-none absolute border-2 border-cyan"
                      style={{
                        left: `${(box.x / width) * 100}%`,
                        top: `${(box.y / height) * 100}%`,
                        width: `${(box.width / width) * 100}%`,
                        height: `${(box.height / height) * 100}%`,
                        transformOrigin: "top left",
                      }}
                      initial={reduceMotion ? false : { opacity: 0, scale: 1.25 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                    >
                      <span className="absolute -top-5 left-0 bg-cyan/20 px-1 font-mono text-2xs text-cyan">
                        MODEL-DERIVED REGION
                      </span>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* scanline while processing */}
                <AnimatePresence>
                  {scanning && !reduceMotion && (
                    <motion.div
                      className="pointer-events-none absolute inset-x-0 h-16 bg-gradient-to-b from-transparent via-cyan/25 to-transparent"
                      initial={{ top: "-15%" }}
                      animate={{ top: ["-15%", "105%"] }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 1.6, repeat: Infinity, ease: "linear" }}
                    />
                  )}
                </AnimatePresence>

                {/* decision stamp */}
                <AnimatePresence>
                  {decision && (
                    <motion.div
                      key={decision}
                      initial={reduceMotion ? false : { opacity: 0, scale: 1.8, rotate: -14 }}
                      animate={{ opacity: 1, scale: 1, rotate: -8 }}
                      transition={{ type: "spring", stiffness: 320, damping: 18 }}
                      className={`absolute right-4 top-4 border-4 px-4 py-2 ${DECISION_STYLE[decision]?.border ?? "border-ink-3"} ${
                        DECISION_STYLE[decision]?.bg ?? "bg-bg/70"
                      } backdrop-blur`}
                    >
                      <p className={`text-xl font-black tracking-[0.18em] ${DECISION_STYLE[decision]?.text ?? "text-ink"}`}>
                        {decision}
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3 py-16 text-center">
                <ScanLine size={26} className="text-ink-3" aria-hidden />
                <p className="text-sm text-ink-2">Drop an inspection image — the pipeline runs live</p>
                <p className="max-w-md text-2xs leading-relaxed text-ink-3">
                  Every stage streams to the interface the moment the backend completes it: validation,
                  preprocessing, feature extraction, classification, anomaly analysis, localization, decision.
                </p>
                <button type="button" className="btn-primary mt-2" onClick={() => inputRef.current?.click()} disabled={inspecting}>
                  <UploadCloud size={12} aria-hidden />
                  Select image
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

          {imageUrl && (
            <footer className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-line px-4 py-2 font-mono text-2xs text-ink-3">
              <span>{width} × {height}</span>
              <span>{inspection?.image_metadata.format ?? "image"}</span>
              <button type="button" className="text-ink-3 hover:text-ink-2" onClick={() => setShowHeatmap((v) => !v)}>
                <Gauge size={10} className="mr-1 inline" aria-hidden />
                heatmap {showHeatmap ? "on" : "off"}
              </button>
              <button type="button" className="text-ink-3 hover:text-ink-2" onClick={() => setShowBox((v) => !v)}>
                <Crosshair size={10} className="mr-1 inline" aria-hidden />
                region {showBox ? "on" : "off"}
              </button>
              <span className="text-novel">LOCALIZATION: MODEL-DERIVED</span>
            </footer>
          )}
        </Panel>

        {/* ---------------- live stage rail ---------------- */}
        <Panel
          title="Live pipeline"
          subtitle={
            liveStatus === "streaming"
              ? "streaming from the backend"
              : liveStatus === "complete"
                ? "inspection complete"
                : "waiting for an image"
          }
        >
          <ol className="flex flex-col">
            {STAGE_ORDER.map((stageId, index) => {
              const stage = byId.get(stageId);
              const isCurrent = stageId === currentStageId && liveStatus === "streaming";
              return (
                <li key={stageId} className="relative">
                  {index < STAGE_ORDER.length - 1 && (
                    <span className="absolute left-[19px] top-7 h-[calc(100%-16px)] w-px bg-line" aria-hidden />
                  )}
                  <motion.div
                    initial={reduceMotion ? false : { opacity: 0, x: 8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.25 }}
                    className={`flex items-start gap-2.5 px-3 py-2 ${isCurrent ? "bg-cyan/5" : ""}`}
                  >
                    <span
                      className={`z-10 flex h-5 w-5 shrink-0 items-center justify-center border font-mono text-2xs ${
                        stage
                          ? stage.status === "not_supported"
                            ? "border-warn/50 text-warn"
                            : "border-ok/50 text-ok"
                          : isCurrent
                            ? "animate-pulse border-cyan/60 text-cyan"
                            : "border-line text-ink-3"
                      }`}
                    >
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className={`text-2xs font-semibold uppercase tracking-[0.1em] ${stage ? "text-ink" : "text-ink-3"}`}>
                          {stage?.label ?? stageId.replace(/_/g, " ")}
                        </span>
                        {stage && <span className="font-mono text-2xs text-ink-3">{stage.duration_ms.toFixed(1)} ms</span>}
                      </span>
                      {stage && <StageValue stage={stage} />}
                    </span>
                  </motion.div>
                </li>
              );
            })}
          </ol>
          <p className="border-t border-line px-3 py-2 text-2xs leading-relaxed text-ink-3">
            Stages arrive as the backend completes them. {cinematic ? "Cinematic pacing holds each stage briefly for readability — the results themselves are not delayed." : "Raw backend speed."}
          </p>
        </Panel>
      </div>

      {/* ---------------- live outputs ---------------- */}
      <div className="grid gap-3 lg:grid-cols-3">
        <Panel title="Class probabilities" subtitle="calibrated output">
          {probabilities ? (
            <ul className="flex flex-col gap-2 px-4 py-3">
              {Object.entries(probabilities)
                .sort((a, b) => b[1] - a[1])
                .map(([name, probability], index) => (
                  <li key={name} className="flex items-center gap-2">
                    <span className="w-16 shrink-0 truncate text-2xs text-ink-2">{name}</span>
                    <span className="h-1.5 flex-1 bg-line">
                      <motion.span
                        className={`block h-full ${index === 0 ? "bg-cyan" : "bg-idle/70"}`}
                        initial={reduceMotion ? false : { width: 0 }}
                        animate={{ width: `${Math.max(probability * 100, 1)}%` }}
                        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
                      />
                    </span>
                    <span className="w-12 shrink-0 text-right font-mono text-2xs text-ink-3">
                      {(probability * 100).toFixed(1)}%
                    </span>
                  </li>
                ))}
            </ul>
          ) : (
            <EmptyLine text="Awaiting classification stage…" />
          )}
        </Panel>

        <Panel title="Anomaly & novelty" subtitle="percentile vs references">
          {anomalyScore !== undefined ? (
            <div className="flex flex-col items-center gap-2 px-4 py-3">
              <AnomalyGauge score={anomalyScore} reduceMotion={Boolean(reduceMotion)} />
              <p className="font-mono text-2xs text-ink-3">
                anomaly {formatNumber(anomalyScore, 3)} · novelty {formatNumber(noveltyScore ?? 0, 3)}{" "}
                <span className={noveltyStatus === "HIGH" ? "text-novel" : "text-ink-2"}>{noveltyStatus}</span>
              </p>
            </div>
          ) : (
            <EmptyLine text="Awaiting anomaly stage…" />
          )}
        </Panel>

        <Panel title="Decision" subtitle="thresholds + confidence">
          {decision ? (
            <div className="flex flex-col gap-2 px-4 py-3">
              <div className={`flex items-center gap-2 border px-3 py-2 ${DECISION_STYLE[decision]?.border ?? "border-line"} ${DECISION_STYLE[decision]?.bg ?? ""}`}>
                {decision === "PASS" ? (
                  <CheckCircle2 size={16} className="text-ok" aria-hidden />
                ) : decision === "DEFECT" ? (
                  <AlertTriangle size={16} className="text-bad" aria-hidden />
                ) : (
                  <CircleHelp size={16} className="text-warn" aria-hidden />
                )}
                <span className={`text-sm font-bold tracking-[0.12em] ${DECISION_STYLE[decision]?.text ?? "text-ink"}`}>{decision}</span>
                {confidence !== undefined && (
                  <span className="ml-auto font-mono text-2xs text-ink-2">
                    {(confidence * 100).toFixed(1)}% {confidenceLevel}
                  </span>
                )}
              </div>
              {reviewReason && <p className="text-2xs leading-relaxed text-warn">{reviewReason}</p>}
              <button
                type="button"
                className="btn-ghost w-fit !px-2 !py-1"
                onClick={() =>
                  inspection &&
                  onOpenEvidence(
                    `Why ${inspection.decision}?`,
                    `${inspection.prediction.predicted_class} · confidence ${(inspection.confidence.value * 100).toFixed(1)}%`,
                    inspection.evidence.map((entry) => ({
                      statement: entry.statement,
                      detail: `source: ${entry.source}`,
                      source_artifact: `vision/${entry.source}`,
                      epistemic_status: entry.epistemic_status,
                    })),
                    inspection.limitations,
                  )
                }
                disabled={!inspection}
              >
                WHY?
              </button>
              {inspection && (
                <p className="text-2xs leading-relaxed text-ink-3">{inspection.process_link.reason}</p>
              )}
            </div>
          ) : (
            <EmptyLine text="Awaiting decision stage…" />
          )}
        </Panel>
      </div>

      {inspection && <ProcessingStrip inspection={inspection} />}
    </div>
  );
}

function StageValue({ stage }: { stage: VisionTraceStage }) {
  const metrics = stage.metrics ?? {};
  let text: string | null = null;
  if (stage.id === "validation" && metrics.width) text = `${metrics.width}×${metrics.height} ${metrics.format}`;
  if (stage.id === "preprocessing" && metrics.resize) text = `${metrics.resize} · normalized`;
  if (stage.id === "feature_extraction" && metrics.embedding_dim) text = `${metrics.embedding_dim}-d embedding`;
  if (stage.id === "classification" && metrics.predicted_class)
    text = `${metrics.predicted_class} ${(((metrics.calibrated_probability as number) ?? 0) * 100).toFixed(1)}%`;
  if (stage.id === "anomaly_analysis" && metrics.anomaly_score !== undefined)
    text = `anomaly ${Number(metrics.anomaly_score).toFixed(3)} · novelty ${Number(metrics.novelty_score ?? 0).toFixed(3)}`;
  if (stage.id === "localization") text = "class-activation map (model-derived)";
  if (stage.id === "confidence" && metrics.confidence_level) text = `${metrics.confidence_level} confidence`;
  if (stage.id === "decision" && metrics.decision) text = String(metrics.decision);
  if (stage.id === "process_link" && metrics.status) text = String(metrics.status);
  if (!text) return null;
  return <span className="mt-0.5 block truncate font-mono text-2xs text-ink-2">{text}</span>;
}

function AnomalyGauge({ score, reduceMotion }: { score: number; reduceMotion: boolean }) {
  const radius = 46;
  const circumference = Math.PI * radius;
  const filled = Math.max(0, Math.min(1, score)) * circumference;
  const tone = score > 0.99 ? "#a78bfa" : score > 0.9 ? "#f0b429" : "#38d6e0";
  return (
    <svg viewBox="0 0 120 70" className="h-20 w-40" role="img" aria-label={`Anomaly score ${score.toFixed(3)}`}>
      <path d="M 14 60 A 46 46 0 0 1 106 60" fill="none" stroke="rgba(148,163,184,0.25)" strokeWidth={8} strokeLinecap="round" />
      <motion.path
        d="M 14 60 A 46 46 0 0 1 106 60"
        fill="none"
        stroke={tone}
        strokeWidth={8}
        strokeLinecap="round"
        strokeDasharray={circumference}
        initial={reduceMotion ? false : { strokeDashoffset: circumference }}
        animate={{ strokeDashoffset: circumference - filled }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      />
      <text x="60" y="52" textAnchor="middle" fill="#e8edf4" fontSize="16" fontFamily="var(--font-mono)">
        {score.toFixed(2)}
      </text>
      <text x="60" y="64" textAnchor="middle" fill="#5f7085" fontSize="8" fontFamily="var(--font-mono)">
        PERCENTILE
      </text>
    </svg>
  );
}

function EmptyLine({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-2 px-4 py-4 text-2xs text-ink-3">
      <Zap size={11} aria-hidden />
      {text}
    </div>
  );
}

function ProcessingStrip({ inspection }: { inspection: VisionInspection }) {
  const preprocessed = inspection.preprocessing.preprocessed_png_base64;
  const heatmap = inspection.localization.heatmap_png_base64;
  const items = [
    {
      label: "ORIGINAL",
      caption: `${inspection.image_metadata.width} × ${inspection.image_metadata.height} ${inspection.image_metadata.format}`,
      src: `${API_BASE}/api/vision/inspect/${inspection.inspection_id}/image`,
      note: "as uploaded",
    },
    {
      label: "PREPROCESSED",
      caption: inspection.preprocessing.resize,
      src: preprocessed ? `data:image/png;base64,${preprocessed}` : null,
      note: "exact tensor the backbone consumed",
    },
    {
      label: "MODEL ANOMALY MAP",
      caption: inspection.localization.method,
      src: heatmap ? `data:image/png;base64,${heatmap}` : null,
      note: "model-derived localization",
    },
  ];
  return (
    <Panel title="Recorded artifacts" subtitle="original → preprocessed tensor → model anomaly map (stored with this inspection)">
      <div className="flex flex-wrap items-start gap-3 px-4 py-3">
        {items.map((item) => (
          <figure key={item.label} className="flex w-32 flex-col gap-1.5">
            {item.src ? (
              <img src={item.src} alt={item.label} className="h-32 w-32 border border-line-2 bg-black object-contain" />
            ) : (
              <div className="flex h-32 w-32 items-center justify-center border border-line bg-black/40 text-2xs text-ink-3">
                not available
              </div>
            )}
            <figcaption>
              <span className="label block">{item.label}</span>
              <span className="block truncate font-mono text-2xs text-ink-2">{item.caption}</span>
              <span className="block truncate text-2xs text-ink-3">{item.note}</span>
            </figcaption>
          </figure>
        ))}
      </div>
    </Panel>
  );
}
