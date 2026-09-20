import { motion, useReducedMotion } from "framer-motion";

import { EvidenceBadge } from "./EvidenceBadge";

export type Recommendation = {
  id: string;
  action: string;
  rationale: string;
  priority: string;
  category?: string | null;
  expected_effect?: string | null;
  epistemic?: string;
  source_signals?: string[] | null;
};

const PRIORITY_TONE: Record<string, string> = {
  high: "border-bad/50 text-bad",
  medium: "border-warn/50 text-warn",
  low: "border-ok/50 text-ok",
};

/** Advisory action card. Recommendations are deterministic rules, not model guesses. */
export function RecommendationCard({ recommendation, index }: { recommendation: Recommendation; index: number }) {
  const reduceMotion = useReducedMotion();
  const priority = (recommendation.priority ?? "medium").toLowerCase();
  return (
    <motion.article
      initial={reduceMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.08 }}
      className="hud flex flex-col gap-2.5 p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <span className={`chip ${PRIORITY_TONE[priority] ?? "border-line-2 text-ink-2"}`}>{recommendation.priority} priority</span>
        <EvidenceBadge status={recommendation.epistemic ?? "ADVISORY"} />
      </div>
      <h3 className="text-sm font-medium leading-snug text-ink">{recommendation.action}</h3>
      <p className="text-2xs leading-relaxed text-ink-2">{recommendation.rationale}</p>
      {recommendation.expected_effect && (
        <p className="border-t border-line/60 pt-2 text-2xs leading-relaxed text-ink-3">
          <span className="label mr-2">expected effect</span>
          {recommendation.expected_effect}
        </p>
      )}
      {recommendation.source_signals && recommendation.source_signals.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {recommendation.source_signals.map((signal) => (
            <span key={signal} className="border border-line/60 px-1.5 py-0.5 font-mono text-[9px] text-ink-3">
              {signal}
            </span>
          ))}
        </div>
      )}
    </motion.article>
  );
}
