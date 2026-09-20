import { motion, useReducedMotion } from "framer-motion";

import { EvidenceBadge } from "./EvidenceBadge";

/** Ranked signals with real scores and their factor breakdown (root cause, bottlenecks). */
export function RankedSignals({
  items,
  emptyText = "no signals computed yet.",
  onSelect,
  selectedId,
}: {
  items: {
    id: string;
    label: string;
    score: number;
    detail: string;
    epistemic: string;
    factors?: { name: string; value: number }[] | null;
    rank?: number;
  }[];
  emptyText?: string;
  onSelect?: (id: string) => void;
  selectedId?: string | null;
}) {
  const reduceMotion = useReducedMotion();
  if (items.length === 0) {
    return <p className="px-4 py-3 text-2xs text-ink-3">{emptyText}</p>;
  }
  const max = Math.max(...items.map((item) => item.score), 0.0001);
  return (
    <ol className="flex flex-col">
      {items.map((item, index) => (
        <motion.li
          key={item.id}
          initial={reduceMotion ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: index * 0.05 }}
          className={`border-b border-line/40 last:border-b-0 ${selectedId === item.id ? "bg-cyan/5" : ""}`}
        >
          <button
            type="button"
            onClick={() => onSelect?.(item.id)}
            disabled={!onSelect}
            className={`flex w-full items-center gap-3 px-4 py-2.5 text-left ${onSelect ? "cursor-pointer transition-colors hover:bg-panel-2/40" : "cursor-default"}`}
            aria-label={onSelect ? `${item.label} — open evidence` : undefined}
          >
            <span className="w-5 shrink-0 font-mono text-2xs text-ink-3">{String(item.rank ?? index + 1).padStart(2, "0")}</span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate text-xs font-medium text-ink">{item.label}</span>
                <EvidenceBadge status={item.epistemic} />
              </div>
              <div className="mt-1.5 h-1 w-full bg-line/50">
                <motion.div
                  className="h-full bg-cyan"
                  initial={reduceMotion ? false : { width: 0 }}
                  animate={{ width: `${(item.score / max) * 100}%` }}
                  transition={{ duration: 0.6, delay: index * 0.05, ease: [0.22, 1, 0.36, 1] }}
                  style={{ boxShadow: "0 0 10px rgb(var(--cyan) / 0.5)" }}
                />
              </div>
              <p className="mt-1 text-2xs leading-relaxed text-ink-3">{item.detail}</p>
            </div>
            <span className="w-14 shrink-0 text-right font-mono text-sm text-ink">{item.score.toFixed(1)}</span>
          </button>
          {item.factors && item.factors.length > 0 && selectedId === item.id && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-line/40 bg-bg-2/40 px-4 py-2 pl-12">
              {item.factors.map((factor) => (
                <span key={factor.name} className="text-2xs text-ink-3">
                  {factor.name.replace(/_/g, " ")}{" "}
                  <span className="font-mono text-ink-2">{factor.value.toFixed(3)}</span>
                </span>
              ))}
            </div>
          )}
        </motion.li>
      ))}
    </ol>
  );
}
