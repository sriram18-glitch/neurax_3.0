import { motion, useReducedMotion } from "framer-motion";
import { ScanSearch } from "lucide-react";

import { useSession } from "../session/SessionContext";
import type { VisionTraceStage } from "../types/api";
import { PipelineFlow, visionTraceToFlow } from "./PipelineFlow";
import { NotAvailable, Panel } from "./ui/Primitives";

const STAGE_LABELS: Record<string, string> = {
  image_received: "Image received",
  validation: "Validation",
  preprocessing: "Preprocessing",
  feature_extraction: "Feature extraction",
  classification: "Classification",
  anomaly_analysis: "Anomaly analysis",
  localization: "Localization",
  confidence: "Confidence",
  decision: "Decision",
  process_link: "Process link",
};

function renderMetricValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function ConsoleView() {
  const { inspection, liveStages, liveStatus } = useSession();
  const reduceMotion = useReducedMotion();
  const trace = liveStages.length > 0 ? liveStages : inspection?.trace ?? [];
  const streaming = liveStatus === "streaming";

  if (trace.length === 0) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-14">
        <Panel title="AI inspection console" subtitle="Observable processing pipeline">
          <div className="px-4 py-4">
            <NotAvailable reason="No inspection has been run yet. Upload an image in the INSPECT area to watch the pipeline execute live." />
          </div>
        </Panel>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-3 p-3">
      <Panel
        title="Processing pipeline"
        subtitle={
          streaming
            ? `streaming live — ${trace.length} stage(s) received`
            : `${trace.length} observable stages · real recorded durations`
        }
        actions={
          streaming ? (
            <span className="chip border-cyan/50 bg-cyan/10 text-cyan">
              <span className="h-1.5 w-1.5 animate-pulse bg-cyan" aria-hidden />
              LIVE
            </span>
          ) : (
            <span className="chip border-line text-ink-3">
              <ScanSearch size={11} aria-hidden />
              {inspection?.model.backbone ?? "model"}
            </span>
          )
        }
      >
        <div className="px-4 py-3">
          <PipelineFlow stages={visionTraceToFlow(trace)} />
        </div>
      </Panel>

      <Panel
        title="AI inspection console"
        subtitle={inspection ? `stage-by-stage outputs · inspection ${inspection.inspection_id}` : "stage-by-stage outputs"}
      >
        <ol className="divide-y divide-line">
          {trace.map((stage, index) => (
            <StageRow key={stage.id} stage={stage} index={index} reduceMotion={Boolean(reduceMotion)} />
          ))}
          {streaming && (
            <li className="flex items-center gap-2 px-4 py-3 text-2xs text-cyan">
              <span className="h-1.5 w-1.5 animate-pulse bg-cyan" aria-hidden />
              waiting for the next stage from the backend…
            </li>
          )}
        </ol>
        <p className="border-t border-line px-4 py-2 text-2xs leading-relaxed text-ink-3">
          These are observable engineering stages and model outputs — not private model chain-of-thought. Every metric
          shown was produced by the backend during this inspection.
        </p>
      </Panel>
    </div>
  );
}

function StageRow({ stage, index, reduceMotion }: { stage: VisionTraceStage; index: number; reduceMotion: boolean }) {
  const entries = Object.entries(stage.metrics ?? {});
  return (
    <motion.li
      initial={reduceMotion ? false : { opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: reduceMotion ? 0 : index * 0.03 }}
      className="px-4 py-3"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span
            className={`flex h-5 w-5 items-center justify-center border font-mono text-2xs ${
              stage.status === "complete"
                ? "border-ok/50 text-ok"
                : stage.status === "not_supported"
                  ? "border-warn/50 text-warn"
                  : "border-bad/50 text-bad"
            }`}
          >
            {String(index + 1).padStart(2, "0")}
          </span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-ink">
              {STAGE_LABELS[stage.id] ?? stage.id}
            </p>
            <p className="text-2xs text-ink-3">{stage.summary}</p>
          </div>
        </div>
        <span className="shrink-0 font-mono text-2xs text-ink-3">
          {stage.status === "complete" ? "✓" : stage.status.toUpperCase()} {stage.duration_ms.toFixed(1)} ms
        </span>
      </div>
      {entries.length > 0 && (
        <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 pl-8 sm:grid-cols-2">
          {entries.map(([key, value]) => (
            <div key={key} className="flex items-baseline justify-between gap-3">
              <dt className="truncate text-2xs text-ink-3">{key.replace(/_/g, " ")}</dt>
              <dd className="truncate text-right font-mono text-2xs text-ink-2">{renderMetricValue(value)}</dd>
            </div>
          ))}
        </dl>
      )}
    </motion.li>
  );
}
