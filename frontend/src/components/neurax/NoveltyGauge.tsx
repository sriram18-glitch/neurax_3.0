import { motion, useReducedMotion } from "framer-motion";

import { EvidenceBadge } from "./EvidenceBadge";

function noveltyState(score: number, decision?: string | null): { label: string; tone: string; detail: string } {
  if (decision === "REVIEW" && score >= 0.95) {
    return {
      label: "REVIEW",
      tone: "text-warn",
      detail: "the sample is unfamiliar enough that the decision moved to human review",
    };
  }
  if (score >= 0.99) {
    return { label: "NOVEL", tone: "text-novel", detail: "far outside the known distribution for its assigned class" };
  }
  if (score >= 0.95) {
    return { label: "UNUSUAL", tone: "text-warn", detail: "near the edge of the known distribution" };
  }
  return { label: "KNOWN", tone: "text-ok", detail: "consistent with the known distribution for its assigned class" };
}

/**
 * Robustness view: where this sample sits relative to the known reference.
 * Novelty is separate from classification confidence and from the anomaly
 * percentile - three different concepts, never merged.
 */
export function NoveltyGauge({
  noveltyScore,
  noveltyStatus,
  anomalyScore,
  decision,
  gate = 0.99,
}: {
  noveltyScore: number | null | undefined;
  noveltyStatus?: string | null;
  anomalyScore?: number | null;
  decision?: string | null;
  gate?: number;
}) {
  const reduceMotion = useReducedMotion();
  if (noveltyScore === null || noveltyScore === undefined) {
    return <p className="px-4 py-3 text-2xs text-ink-3">awaiting robustness output…</p>;
  }
  const state = noveltyState(noveltyScore, decision);

  return (
    <div className="flex flex-col gap-3 px-4 py-3">
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="label">known distribution</span>
          <EvidenceBadge status="MODEL OUTPUT" />
        </div>
        <div className="relative h-9 border border-line/60 bg-bg-2/50">
          <div className="absolute inset-y-0 left-0 bg-ok/15" style={{ width: "95%" }} />
          <div className="absolute inset-y-0 bg-warn/15" style={{ left: "95%", right: `${(1 - gate) * 100}%` }} />
          <div className="absolute inset-y-0 right-0 bg-novel/15" style={{ width: `${(1 - gate) * 100}%` }} />
          <div className="absolute inset-y-0 border-l border-dashed border-warn/60" style={{ left: "95%" }} />
          <div className="absolute inset-y-0 border-l border-dashed border-novel/60" style={{ left: `${gate * 100}%` }} />
          <motion.div
            className="absolute top-0 bottom-0 w-0.5 bg-ink"
            initial={reduceMotion ? false : { left: 0 }}
            animate={{ left: `${Math.min(1, Math.max(0, noveltyScore)) * 100}%` }}
            transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
            style={{ boxShadow: "0 0 10px rgba(232,237,244,0.7)" }}
          >
            <span className="absolute -top-4 left-1/2 -translate-x-1/2 whitespace-nowrap font-mono text-[9px] text-ink-2">
              current
            </span>
          </motion.div>
          <span className="absolute bottom-0.5 left-1 font-mono text-[9px] text-ok/80">known</span>
          <span className="absolute bottom-0.5 font-mono text-[9px] text-warn/80" style={{ left: "95.5%" }}>
            unusual
          </span>
          <span className="absolute bottom-0.5 right-1 font-mono text-[9px] text-novel/80">novel</span>
        </div>
        <p className="mt-2 flex items-baseline gap-2">
          <span className={`font-mono text-sm ${state.tone}`}>{state.label}</span>
          <span className="text-2xs text-ink-3">{state.detail}</span>
        </p>
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-line/60 pt-2">
        <div>
          <p className="label">novelty score</p>
          <p className="font-mono text-xs text-ink-2">
            {noveltyScore.toFixed(3)} <span className="text-ink-3">· {noveltyStatus ?? "—"}</span>
          </p>
        </div>
        {anomalyScore !== null && anomalyScore !== undefined && (
          <div className="text-right">
            <p className="label">anomaly percentile (separate)</p>
            <p className="font-mono text-xs text-ink-2">{anomalyScore.toFixed(3)}</p>
          </div>
        )}
      </div>
      <p className="text-2xs leading-relaxed text-ink-3">
        Novelty compares the sample against the known class it was assigned to; the anomaly percentile compares it against
        the normal reference. Neither is a probability, and neither replaces classification confidence.
      </p>
    </div>
  );
}
