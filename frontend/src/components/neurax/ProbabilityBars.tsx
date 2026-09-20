import { motion, useReducedMotion } from "framer-motion";

/** Animated class probabilities from the calibrated classifier output. */
export function ProbabilityBars({
  probabilities,
  winner,
}: {
  probabilities: Record<string, number> | null | undefined;
  winner?: string | null;
}) {
  const reduceMotion = useReducedMotion();
  if (!probabilities || Object.keys(probabilities).length === 0) {
    return <p className="px-4 py-4 text-2xs text-ink-3">awaiting classification output…</p>;
  }
  const sorted = Object.entries(probabilities).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...sorted.map(([, value]) => value), 0.0001);
  return (
    <ul className="flex w-full min-w-0 flex-col gap-2.5">
      {sorted.map(([name, probability], index) => {
        const isWinner = name === winner || (winner === undefined && index === 0);
        return (
          <li key={name} className="flex items-center gap-3">
            <span className={`w-20 shrink-0 truncate font-mono text-2xs uppercase ${isWinner ? "text-cyan" : "text-ink-3"}`}>
              {name}
            </span>
            <span className="relative h-2 flex-1 overflow-hidden bg-line/50">
              <motion.span
                className={`absolute inset-y-0 left-0 ${isWinner ? "bg-cyan" : "bg-idle/60"}`}
                initial={reduceMotion ? false : { width: 0 }}
                animate={{ width: `${(probability / max) * 100}%` }}
                transition={{ duration: 0.7, delay: reduceMotion ? 0 : index * 0.06, ease: [0.22, 1, 0.36, 1] }}
                style={isWinner ? { boxShadow: "0 0 12px rgb(var(--cyan) / 0.6)" } : undefined}
              />
            </span>
            <span className={`w-14 shrink-0 text-right font-mono text-2xs ${isWinner ? "text-ink" : "text-ink-3"}`}>
              {(probability * 100).toFixed(1)}%
            </span>
          </li>
        );
      })}
    </ul>
  );
}
