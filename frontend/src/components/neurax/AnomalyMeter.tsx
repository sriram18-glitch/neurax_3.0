import { motion, useReducedMotion } from "framer-motion";

import { EvidenceBadge } from "./EvidenceBadge";

/**
 * Anomaly vs novelty. The anomaly score is a percentile against the normal
 * reference (never presented as a probability); novelty compares against the
 * assigned known class.
 */
export function AnomalyMeter({
  anomalyScore,
  noveltyScore,
  noveltyStatus,
  gate,
}: {
  anomalyScore: number | null | undefined;
  noveltyScore?: number | null;
  noveltyStatus?: string | null;
  gate?: number | null;
}) {
  const reduceMotion = useReducedMotion();
  if (anomalyScore === null || anomalyScore === undefined) {
    return <p className="px-4 py-4 text-2xs text-ink-3">awaiting anomaly output…</p>;
  }
  const gateValue = gate ?? 0.99;
  return (
    <div className="flex flex-col gap-3 px-4 py-3">
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="label">normal reference region</span>
          <span className="font-mono text-2xs text-ink-3">0 → {gateValue.toFixed(2)}</span>
        </div>
        <div className="relative h-6">
          <div className="absolute inset-x-0 top-2 h-2 bg-cyan/15" />
          <div className="absolute top-1.5 h-3 bg-cyan/30" style={{ width: `${gateValue * 100}%` }} />
          <motion.div
            className="absolute top-0 h-6 w-0.5 bg-novel"
            initial={reduceMotion ? false : { left: 0 }}
            animate={{ left: `${Math.min(anomalyScore, 1) * 100}%` }}
            transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
            style={{ boxShadow: "0 0 10px rgb(var(--violet) / 0.8)" }}
          />
        </div>
        <div className="mt-1 flex items-center justify-between">
          <span className="text-2xs text-ink-3">feature distance percentile</span>
          <span className="font-mono text-2xs text-ink-2">anomaly {anomalyScore.toFixed(3)}</span>
        </div>
      </div>

      {noveltyScore !== undefined && noveltyScore !== null && (
        <div className="flex items-center justify-between gap-3 border-t border-line/60 pt-2.5">
          <div>
            <p className="label">novelty vs assigned class</p>
            <p className="font-mono text-xs text-ink-2">
              {noveltyScore.toFixed(3)}{" "}
              <span className={noveltyStatus === "HIGH" ? "text-novel" : "text-ink-3"}>{noveltyStatus}</span>
            </p>
          </div>
          <EvidenceBadge status="MODEL OUTPUT" />
        </div>
      )}
      <p className="text-2xs leading-relaxed text-ink-3">
        anomaly score is a percentile against the normal reference — not a probability
      </p>
    </div>
  );
}
