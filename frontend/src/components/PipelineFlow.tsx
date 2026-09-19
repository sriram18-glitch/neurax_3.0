import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight } from "lucide-react";

export interface FlowStage {
  id: string;
  label: string;
  status: string;
  duration_ms?: number | null;
  detail?: string | null;
}

/**
 * Visual pipeline flow: shows the observable processing stages in order with
 * their real recorded durations. Values come from the backend trace; nothing
 * here is simulated.
 */
export function PipelineFlow({ stages, compact = false }: { stages: FlowStage[]; compact?: boolean }) {
  const reduceMotion = useReducedMotion();
  return (
    <div className="flex items-stretch gap-0 overflow-x-auto py-1">
      {stages.map((stage, index) => {
        const failed = stage.status === "failed";
        const notSupported = stage.status === "not_supported";
        const tone = failed
          ? "border-bad/50 bg-bad/5 text-bad"
          : notSupported
            ? "border-warn/40 bg-warn/5 text-warn"
            : "border-ok/40 bg-ok/5 text-ok";
        return (
          <div key={stage.id} className="flex shrink-0 items-center">
            <motion.div
              initial={reduceMotion ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: reduceMotion ? 0 : index * 0.05 }}
              className={`flex ${compact ? "w-28" : "w-36"} flex-col gap-1 border px-2.5 py-2 ${tone}`}
            >
              <span className="font-mono text-2xs opacity-70">{String(index + 1).padStart(2, "0")}</span>
              <span className="text-2xs font-semibold uppercase leading-tight tracking-[0.06em]">
                {stage.label}
              </span>
              {stage.duration_ms !== null && stage.duration_ms !== undefined && (
                <span className="font-mono text-2xs text-ink-3">{stage.duration_ms.toFixed(0)} ms</span>
              )}
              {stage.detail && <span className="truncate font-mono text-2xs text-ink-3">{stage.detail}</span>}
            </motion.div>
            {index < stages.length - 1 && (
              <ArrowRight size={12} className="mx-0.5 shrink-0 text-ink-3" aria-hidden />
            )}
          </div>
        );
      })}
    </div>
  );
}

export function visionTraceToFlow(trace: Array<{ id: string; status: string; duration_ms: number; summary: string; metrics: Record<string, unknown> }>): FlowStage[] {
  const labels: Record<string, string> = {
    image_received: "Image",
    validation: "Validate",
    preprocessing: "Preprocess",
    feature_extraction: "Features",
    classification: "Classify",
    anomaly_analysis: "Anomaly",
    localization: "Localize",
    confidence: "Confidence",
    decision: "Decision",
    process_link: "Link",
  };
  return trace.map((stage) => {
    const metrics = stage.metrics ?? {};
    let detail: string | null = null;
    if (stage.id === "classification" && metrics.predicted_class) {
      detail = `${metrics.predicted_class} ${(((metrics.calibrated_probability as number) ?? 0) * 100).toFixed(0)}%`;
    } else if (stage.id === "anomaly_analysis" && metrics.anomaly_score !== undefined) {
      detail = `score ${Number(metrics.anomaly_score).toFixed(2)}`;
    } else if (stage.id === "decision" && metrics.decision) {
      detail = String(metrics.decision);
    } else if (stage.id === "feature_extraction" && metrics.embedding_dim) {
      detail = `${metrics.embedding_dim}-d`;
    } else if (stage.id === "validation" && metrics.width) {
      detail = `${metrics.width}x${metrics.height}`;
    }
    return {
      id: stage.id,
      label: labels[stage.id] ?? stage.id,
      status: stage.status,
      duration_ms: stage.duration_ms,
      detail,
    };
  });
}
