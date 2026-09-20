import { motion } from "framer-motion";

export type ChainStepId = "what" | "where" | "certain" | "why" | "flow" | "impact" | "next";

export interface ChainStep {
  id: ChainStepId;
  label: string;
  question: string;
  status: "complete" | "partial" | "waiting";
  detail: string;
  result?: string | null;
  source?: string | null;
}

const TONE: Record<ChainStep["status"], { border: string; text: string; dot: string }> = {
  complete: { border: "border-ok/40", text: "text-ok", dot: "bg-ok" },
  partial: { border: "border-warn/40", text: "text-warn", dot: "bg-warn" },
  waiting: { border: "border-line", text: "text-ink-3", dot: "bg-idle" },
};

/**
 * Persistent decision chain: WHAT → WHERE → HOW CERTAIN → WHY → FLOW →
 * IMPACT → WHAT NEXT. Clicking a step navigates to its evidence section.
 */
export function DecisionChain({ steps, onSelect }: { steps: ChainStep[]; onSelect?: (id: ChainStepId) => void }) {
  return (
    <ol className="flex flex-col">
      {steps.map((step, index) => {
        const tone = TONE[step.status];
        return (
          <li key={step.id} className="relative">
            {index < steps.length - 1 && <span className="absolute left-[22px] top-9 bottom-0 w-px bg-line-2" aria-hidden />}
            <button
              type="button"
              onClick={() => onSelect?.(step.id)}
              className="flex w-full items-start gap-3 px-4 py-2.5 text-left transition-colors hover:bg-panel-2/40"
            >
              <span className="relative z-10 flex h-4 w-4 shrink-0 items-center justify-center border border-line-2 bg-bg">
                <span className={`h-1.5 w-1.5 ${tone.dot}`} aria-hidden />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-baseline gap-2">
                  <span className={`font-mono text-2xs uppercase tracking-[0.12em] ${tone.text}`}>{step.label}</span>
                  <span className="text-[9px] text-ink-3">{step.question}</span>
                </span>
                {step.result && (
                  <span className={`mt-0.5 block truncate font-mono text-xs ${tone.text}`}>{step.result}</span>
                )}
                <span className="mt-0.5 block truncate text-2xs text-ink-2">{step.detail}</span>
                {step.source && <span className="mt-0.5 block truncate text-[9px] text-ink-3">source: {step.source}</span>}
              </span>
              <motion.span
                className={`mt-0.5 font-mono text-[9px] uppercase ${tone.text}`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.3, delay: index * 0.04 }}
              >
                {step.status}
              </motion.span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
