/**
 * Epistemic badge system: every result carries how it is known.
 * Markers are shape-coded as well as colored (accessibility).
 */

export type Epistemic =
  | "OBSERVED"
  | "MODEL OUTPUT"
  | "MODEL-DERIVED"
  | "STATISTICAL ASSOCIATION"
  | "USER ASSUMPTION"
  | "SIMULATION"
  | "CALCULATED"
  | "ADVISORY"
  | "NOT AVAILABLE";

const STYLES: Record<string, { text: string; border: string; dot: string; shape: string }> = {
  OBSERVED: { text: "text-ink-2", border: "border-line-2", dot: "bg-ink-2", shape: "rounded-full" },
  "MODEL OUTPUT": { text: "text-cyan", border: "border-cyan/40", dot: "bg-cyan", shape: "rounded-sm" },
  "MODEL-DERIVED": { text: "text-cyan", border: "border-cyan/30", dot: "bg-cyan/70", shape: "rounded-sm" },
  "STATISTICAL ASSOCIATION": { text: "text-novel", border: "border-novel/40", dot: "bg-novel", shape: "rounded-full" },
  "USER ASSUMPTION": { text: "text-warn", border: "border-warn/40", dot: "bg-warn", shape: "rounded-none" },
  SIMULATION: { text: "text-warn", border: "border-warn/30", dot: "bg-warn/70", shape: "rounded-none" },
  CALCULATED: { text: "text-ok", border: "border-ok/40", dot: "bg-ok", shape: "rounded-sm" },
  ADVISORY: { text: "text-cyan", border: "border-cyan/40", dot: "bg-cyan", shape: "rounded-full" },
  "NOT AVAILABLE": { text: "text-ink-3", border: "border-line", dot: "bg-idle", shape: "rounded-none" },
};

export function EvidenceBadge({ status, className = "" }: { status: string; className?: string }) {
  const style = STYLES[status] ?? STYLES["NOT AVAILABLE"];
  return (
    <span
      className={`inline-flex items-center gap-1.5 border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.1em] ${style.border} ${style.text} ${className}`}
    >
      <span className={`h-1 w-1 ${style.dot} ${style.shape}`} aria-hidden />
      {status}
    </span>
  );
}

export function Legend() {
  const items = ["MODEL OUTPUT", "MODEL-DERIVED", "STATISTICAL ASSOCIATION", "USER ASSUMPTION", "SIMULATION", "OBSERVED"];
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      {items.map((item) => (
        <EvidenceBadge key={item} status={item} />
      ))}
    </div>
  );
}
