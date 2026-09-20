import { motion, useReducedMotion } from "framer-motion";

import { EvidenceBadge } from "./EvidenceBadge";

export type TraceStep = {
  label: string;
  detail: string;
  epistemic: string;
};

/** Vertical data-lineage trace: how the decision was produced, step by step. */
export function DecisionTrace({ steps }: { steps: TraceStep[] }) {
  const reduceMotion = useReducedMotion();
  if (steps.length === 0) {
    return <p className="px-4 py-3 text-2xs text-ink-3">no trace recorded for this run.</p>;
  }
  return (
    <ol className="relative flex flex-col gap-0 px-4 py-2">
      {steps.map((step, index) => (
        <motion.li
          key={`${step.label}-${index}`}
          initial={reduceMotion ? false : { opacity: 0, x: -6 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.3, delay: index * 0.06 }}
          className="relative flex gap-3 pb-4 pl-1 last:pb-1"
        >
          <span className="relative flex w-4 shrink-0 justify-center">
            <span className="mt-1 h-1.5 w-1.5 rounded-full bg-cyan/70" />
            {index < steps.length - 1 && <span className="absolute top-3 bottom-0 w-px bg-line-2" />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-2xs uppercase tracking-[0.1em] text-ink-2">{step.label}</span>
              <EvidenceBadge status={step.epistemic} />
            </div>
            <p className="mt-0.5 text-2xs leading-relaxed text-ink-3">{step.detail}</p>
          </div>
        </motion.li>
      ))}
    </ol>
  );
}
