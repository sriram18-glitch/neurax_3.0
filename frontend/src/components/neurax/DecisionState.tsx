import { motion, useReducedMotion } from "framer-motion";

import { EvidenceBadge } from "./EvidenceBadge";
import { AnimatedNumber } from "./Motion";

export type Decision = "PASS" | "DEFECT" | "REVIEW";

const TONE: Record<Decision, { text: string; glow: string; bg: string; border: string }> = {
  PASS: { text: "text-ok", glow: "text-glow-ok", bg: "bg-ok/10", border: "border-ok/50" },
  DEFECT: { text: "text-bad", glow: "text-glow-bad", bg: "bg-bad/10", border: "border-bad/50" },
  REVIEW: { text: "text-warn", glow: "text-glow-warn", bg: "bg-warn/10", border: "border-warn/50" },
};

/** The decision state machine: PASS / DEFECT / REVIEW with the real thresholds. */
export function DecisionState({
  decision,
  reason,
  confidence,
  thresholds,
}: {
  decision: Decision | null | undefined;
  reason?: string | null;
  confidence?: number | null;
  thresholds?: { pass_confidence?: number; defect_confidence?: number; anomaly_review_percentile?: number } | null;
}) {
  const reduceMotion = useReducedMotion();
  if (!decision) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-8">
        <div className="h-10 w-40 border border-dashed border-line-2" />
        <p className="text-2xs uppercase tracking-[0.16em] text-ink-3">awaiting decision</p>
      </div>
    );
  }
  const tone = TONE[decision];
  const pass = thresholds?.pass_confidence ?? 0.8;
  const defect = thresholds?.defect_confidence ?? 0.7;
  const gate = thresholds?.anomaly_review_percentile ?? 0.99;
  const position = confidence === null || confidence === undefined ? null : Math.min(1, Math.max(0, confidence));

  return (
    <div className="flex flex-col gap-4 px-4 py-4">
      <div className="flex items-center gap-4">
        <motion.div
          initial={reduceMotion ? false : { scale: 0.92, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          className={`flex h-16 w-44 items-center justify-center border ${tone.border} ${tone.bg}`}
        >
          <span className={`font-mono text-2xl font-semibold tracking-[0.18em] ${tone.text} ${tone.glow}`}>{decision}</span>
        </motion.div>
        <div className="min-w-0">
          <p className="label">why this state</p>
          <p className="mt-1 text-2xs leading-relaxed text-ink-2">{reason ?? "decision rule output"}</p>
        </div>
      </div>

      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="label">threshold positions</span>
          <EvidenceBadge status="MODEL OUTPUT" />
        </div>
        <div className="relative h-8 border border-line/60 bg-bg-2/50">
          <div className="absolute inset-y-0 left-0 bg-bad/15" style={{ width: `${defect * 100}%` }} />
          <div className="absolute inset-y-0 bg-ok/15" style={{ left: `${pass * 100}%`, right: 0 }} />
          <div className="absolute inset-y-0 border-l border-dashed border-warn/70" style={{ left: `${defect * 100}%` }} />
          <div className="absolute inset-y-0 border-l border-dashed border-ok/70" style={{ left: `${pass * 100}%` }} />
          {position !== null && (
            <motion.div
              className="absolute inset-y-0 w-0.5 bg-ink"
              initial={reduceMotion ? false : { left: 0 }}
              animate={{ left: `${position * 100}%` }}
              transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
              style={{ boxShadow: "0 0 10px rgba(232,237,244,0.7)" }}
            >
              <span className="absolute -top-1 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-ink" />
            </motion.div>
          )}
          <span className="absolute bottom-0.5 left-1 font-mono text-[9px] text-bad/80">defect &lt; {defect.toFixed(2)}</span>
          <span className="absolute bottom-0.5 right-1 font-mono text-[9px] text-ok/80">pass ≥ {pass.toFixed(2)}</span>
        </div>
        <p className="mt-1.5 text-2xs text-ink-3">
          review is forced when the anomaly percentile exceeds {gate.toFixed(2)} or confidence falls between the two thresholds
          {position !== null && (
            <>
              {" "}
              · this sample: <AnimatedNumber value={position * 100} digits={1} suffix="%" className="text-ink-2" />
            </>
          )}
        </p>
      </div>
    </div>
  );
}
