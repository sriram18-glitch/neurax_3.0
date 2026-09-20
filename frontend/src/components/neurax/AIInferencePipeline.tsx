import { motion, useReducedMotion } from "framer-motion";
import { Activity, Crosshair, Crop, Gavel, Image as ImageIcon, Layers, ShieldCheck, Tag } from "lucide-react";
import { useMemo, useState } from "react";

import type { VisionInspection, VisionTraceStage } from "../../types/api";
import { EvidenceBadge } from "./EvidenceBadge";

type StageState = "WAITING" | "PROCESSING" | "COMPLETE" | "REVIEW" | "NOT_AVAILABLE" | "FAILED";

interface NodeSpec {
  id: string;
  label: string;
  icon: typeof ImageIcon;
  traceIds: string[];
  epistemic: string;
}

const NODES: NodeSpec[] = [
  { id: "image", label: "Image", icon: ImageIcon, traceIds: ["image_received", "validation"], epistemic: "OBSERVED" },
  { id: "preprocess", label: "Preprocess", icon: Crop, traceIds: ["preprocessing"], epistemic: "MODEL OUTPUT" },
  { id: "features", label: "Features", icon: Layers, traceIds: ["feature_extraction"], epistemic: "MODEL OUTPUT" },
  { id: "classify", label: "Classify", icon: Tag, traceIds: ["classification"], epistemic: "MODEL OUTPUT" },
  { id: "anomaly", label: "Anomaly", icon: Activity, traceIds: ["anomaly_analysis"], epistemic: "MODEL OUTPUT" },
  { id: "localize", label: "Localize", icon: Crosshair, traceIds: ["localization"], epistemic: "MODEL-DERIVED" },
  { id: "robustness", label: "Robustness", icon: ShieldCheck, traceIds: ["confidence"], epistemic: "MODEL OUTPUT" },
  { id: "decision", label: "Decision", icon: Gavel, traceIds: ["decision", "process_link"], epistemic: "MODEL OUTPUT" },
];

const STATE_STYLE: Record<StageState, { chip: string; dot: string }> = {
  WAITING: { chip: "text-ink-3 border-line", dot: "bg-idle" },
  PROCESSING: { chip: "text-cyan border-cyan/50 bg-cyan/10", dot: "bg-cyan pulse-ring" },
  COMPLETE: { chip: "text-ok border-ok/40", dot: "bg-ok" },
  REVIEW: { chip: "text-warn border-warn/40", dot: "bg-warn" },
  NOT_AVAILABLE: { chip: "text-ink-3 border-line-2", dot: "bg-idle" },
  FAILED: { chip: "text-bad border-bad/40", dot: "bg-bad" },
};

function plainResult(nodeId: string, inspection: VisionInspection): { text: string; state: StageState } {
  const metadata = inspection.image_metadata;
  const novelty = inspection.anomaly_score.novelty_score;
  const noveltyLabel = novelty >= 0.99 ? "NOVEL" : novelty >= 0.95 ? "UNUSUAL" : "KNOWN";
  switch (nodeId) {
    case "image":
      return { text: `${metadata.width}×${metadata.height} ${metadata.format} received`, state: "COMPLETE" };
    case "preprocess":
      return { text: `resized to ${inspection.preprocessing.resize} and normalized`, state: "COMPLETE" };
    case "features":
      return { text: `frozen backbone produced a ${inspection.feature_vector?.dim ?? "1280"}-d embedding`, state: "COMPLETE" };
    case "classify":
      return {
        text: `${inspection.prediction.predicted_class} · ${(inspection.confidence.value * 100).toFixed(1)}% calibrated probability`,
        state: "COMPLETE",
      };
    case "anomaly":
      return {
        text: `percentile ${inspection.anomaly_score.value.toFixed(3)} against the normal reference`,
        state: "COMPLETE",
      };
    case "localize":
      return inspection.localization.bounding_box
        ? { text: "attention region derived from the class-activation map", state: "COMPLETE" }
        : { text: "no attention region produced for this sample", state: "NOT_AVAILABLE" };
    case "robustness":
      return {
        text: `novelty ${novelty.toFixed(3)} — ${noveltyLabel} (${inspection.anomaly_score.novelty_status})`,
        state: inspection.decision === "REVIEW" ? "REVIEW" : "COMPLETE",
      };
    case "decision":
      return {
        text: inspection.review_reason ?? `${inspection.decision} — decision thresholds satisfied on calibrated output`,
        state: inspection.decision === "REVIEW" ? "REVIEW" : inspection.decision === "DEFECT" ? "COMPLETE" : "COMPLETE",
      };
    default:
      return { text: "—", state: "NOT_AVAILABLE" };
  }
}

/**
 * Visual AI inference pipeline. Plain-language output on the surface;
 * the raw metrics live behind "View technical evidence".
 */
export function AIInferencePipeline({
  inspection,
  liveStages,
  streaming,
  activeStageId,
  onTechnical,
}: {
  inspection: VisionInspection | null;
  liveStages: VisionTraceStage[];
  streaming: boolean;
  activeStageId: string | null;
  onTechnical: (stageId: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const reduceMotion = useReducedMotion();

  const byId = useMemo(() => {
    const map = new Map<string, VisionTraceStage>();
    const source = liveStages.length > 0 ? liveStages : (inspection?.trace ?? []);
    for (const stage of source) map.set(stage.id, stage);
    return map;
  }, [liveStages, inspection]);

  const nodeStates = NODES.map((node) => {
    const stages = node.traceIds.map((id) => byId.get(id)).filter(Boolean) as VisionTraceStage[];
    const done = stages.length === node.traceIds.length;
    const active = node.traceIds.includes(activeStageId ?? "");
    const failed = stages.some((stage) => stage.status === "failed");
    const notSupported = done && stages.every((stage) => stage.status === "not_supported");
    const plain = inspection && done ? plainResult(node.id, inspection) : null;
    let state: StageState = "WAITING";
    if (failed) state = "FAILED";
    else if (active && streaming) state = "PROCESSING";
    else if (done && notSupported) state = "NOT_AVAILABLE";
    else if (done && plain) state = plain.state;
    else if (done) state = "COMPLETE";
    return { node, state, stages, plain };
  });

  const current = nodeStates.find((entry) => entry.node.id === selected) ?? null;

  return (
    <div className="flex flex-col">
      <div className="flex items-stretch gap-1 overflow-x-auto px-3 py-3">
        {nodeStates.map(({ node, state }, index) => {
          const Icon = node.icon;
          const style = STATE_STYLE[state];
          const isOpen = selected === node.id;
          return (
            <div key={node.id} className="flex min-w-0 flex-1 items-center gap-1">
              <button
                type="button"
                onClick={() => setSelected(isOpen ? null : node.id)}
                aria-expanded={isOpen}
                className={`flex min-w-[92px] flex-1 flex-col items-start gap-1 border px-2.5 py-2 text-left transition-all duration-200 ${
                  isOpen ? "border-cyan/60 bg-cyan/5" : `${style.chip.split(" ").slice(1).join(" ")} hover:border-cyan/40`
                }`}
              >
                <span className="flex w-full items-center justify-between">
                  <Icon size={11} className={state === "PROCESSING" ? "text-cyan" : state === "COMPLETE" ? "text-ok" : state === "REVIEW" ? "text-warn" : "text-ink-3"} aria-hidden />
                  <span className={`h-1.5 w-1.5 ${style.dot}`} aria-hidden />
                </span>
                <span className="text-2xs font-semibold uppercase tracking-[0.1em] text-ink-2">{node.label}</span>
                <span className="font-mono text-[9px] tracking-[0.06em] text-ink-3">{state.replace("_", " ")}</span>
              </button>
              {index < nodeStates.length - 1 && (
                <span className="relative h-px w-2.5 shrink-0 bg-line-2" aria-hidden>
                  {state === "COMPLETE" && (
                    <motion.span
                      className="absolute inset-0 bg-cyan/60"
                      initial={reduceMotion ? false : { scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ duration: 0.25, delay: index * 0.03 }}
                      style={{ transformOrigin: "left" }}
                    />
                  )}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {current && (
        <motion.div
          initial={reduceMotion ? false : { opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          className="overflow-hidden border-t border-line/60"
        >
          <div className="flex flex-col gap-2 px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-2xs font-semibold uppercase tracking-[0.12em] text-ink">{current.node.label}</span>
              <span className={`chip ${STATE_STYLE[current.state].chip}`}>{current.state.replace("_", " ")}</span>
              <EvidenceBadge status={current.node.epistemic} />
              <span className="ml-auto flex items-center gap-2">
                {current.stages[0]?.duration_ms !== undefined && (
                  <span className="font-mono text-2xs text-ink-3">{current.stages[0].duration_ms.toFixed(1)} ms</span>
                )}
                <button type="button" className="btn-ghost !px-2 !py-1" onClick={() => onTechnical(current.node.id)}>
                  View technical evidence
                </button>
              </span>
            </div>
            <p className="text-2xs leading-relaxed text-ink-2">
              {current.plain?.text ??
                (streaming ? "Processing — the observable output appears the moment this stage completes." : "No result recorded for this stage.")}
            </p>
          </div>
        </motion.div>
      )}

      <p className="border-t border-line/60 px-4 py-2 text-2xs leading-relaxed text-ink-3">
        {streaming
          ? "Live: stages light up as the backend completes them. "
          : "Recorded: stages come from the stored trace of this inspection. "}
        Observable engineering outputs only — not private model chain-of-thought. Raw metrics are behind “View technical evidence”.
      </p>
    </div>
  );
}

export const PIPELINE_NODE_TRACE: Record<string, string[]> = Object.fromEntries(NODES.map((node) => [node.id, node.traceIds]));
