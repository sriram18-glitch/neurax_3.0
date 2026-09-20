import { motion, useReducedMotion } from "framer-motion";
import { Lock, ShieldCheck, User } from "lucide-react";

/**
 * The automation gate: high confidence + familiar sample → automatic decision;
 * low confidence or novel/out-of-distribution → the automatic decision is
 * blocked and the item escalates to human review.
 */
export function AutomationGate({
  decision,
  confidence,
  noveltyScore,
  noveltyStatus,
}: {
  decision?: string | null;
  confidence?: number | null;
  noveltyScore?: number | null;
  noveltyStatus?: string | null;
}) {
  const reduceMotion = useReducedMotion();
  if (decision !== "REVIEW") {
    return (
      <div className="flex items-center gap-3 border border-ok/30 bg-ok/5 px-4 py-2.5">
        <ShieldCheck size={14} className="shrink-0 text-ok" aria-hidden />
        <div>
          <p className="font-mono text-2xs uppercase tracking-[0.12em] text-ok">Automatic decision</p>
          <p className="mt-0.5 text-2xs text-ink-3">
            confidence {(confidence ?? 0) * 100 === 0 ? "—" : `${((confidence ?? 0) * 100).toFixed(1)}%`} · novelty{" "}
            {noveltyScore !== null && noveltyScore !== undefined ? noveltyScore.toFixed(3) : "—"} ({noveltyStatus ?? "—"})
          </p>
        </div>
      </div>
    );
  }
  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex items-start gap-3 border border-warn/50 bg-warn/10 px-4 py-2.5"
    >
      <Lock size={14} className="mt-0.5 shrink-0 text-warn" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-mono text-2xs uppercase tracking-[0.12em] text-warn">Automatic decision blocked</p>
        <p className="mt-0.5 text-2xs leading-relaxed text-ink-2">
          confidence {(confidence ?? 0) * 100 === 0 ? "—" : `${((confidence ?? 0) * 100).toFixed(1)}%`} · novelty{" "}
          {noveltyScore !== null && noveltyScore !== undefined ? noveltyScore.toFixed(3) : "—"} ({noveltyStatus ?? "—"})
        </p>
        <p className="mt-1 flex items-center gap-1.5 font-mono text-2xs uppercase tracking-[0.12em] text-warn">
          <User size={11} aria-hidden />
          Human review required
        </p>
      </div>
    </motion.div>
  );
}