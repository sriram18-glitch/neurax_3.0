import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useState } from "react";

export type PipelineStage = {
  name: string;
  status: "pending" | "active" | "complete";
  duration_ms?: number | null;
  metrics?: Record<string, unknown> | null;
};

const LABELS: Record<string, string> = {
  intake: "intake",
  validation: "validate",
  preprocessing: "preprocess",
  feature_extraction: "backbone",
  classification: "classify",
  anomaly_analysis: "anomaly",
  novelty_check: "novelty",
  localization: "localize",
  decision: "decide",
  persist: "record",
};

/** Interactive pipeline rail: click a node to open its real outputs. */
export function ProcessingPipeline({
  stages,
  activeStage,
}: {
  stages: PipelineStage[];
  activeStage?: string | null;
}) {
  const [openStage, setOpenStage] = useState<string | null>(null);
  const reduceMotion = useReducedMotion();
  const open = stages.find((stage) => stage.name === openStage) ?? null;

  return (
    <div className="flex flex-col">
      <div className="flex items-stretch gap-1 overflow-x-auto px-4 py-3">
        {stages.map((stage, index) => {
          const complete = stage.status === "complete";
          const active = stage.name === activeStage || stage.status === "active";
          return (
            <div key={stage.name} className="flex min-w-0 flex-1 items-center gap-1">
              <button
                type="button"
                onClick={() => setOpenStage((current) => (current === stage.name ? null : stage.name))}
                className={`group flex min-w-[74px] flex-1 flex-col items-start gap-1 border px-2.5 py-2 text-left transition-all duration-200 ${
                  active
                    ? "border-cyan/60 bg-cyan/10"
                    : complete
                      ? "border-line-2 bg-panel-2/50 hover:border-cyan/40"
                      : "border-line/50 opacity-50"
                }`}
                aria-expanded={openStage === stage.name}
              >
                <span className="flex w-full items-center justify-between">
                  <span className={`font-mono text-[9px] ${active ? "text-cyan" : complete ? "text-ink-2" : "text-ink-3"}`}>
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span
                    className={`h-1.5 w-1.5 ${active ? "bg-cyan pulse-ring" : complete ? "bg-ok" : "bg-idle"}`}
                    aria-hidden
                  />
                </span>
                <span className={`truncate text-2xs uppercase tracking-[0.08em] ${active ? "text-cyan" : "text-ink-2"}`}>
                  {LABELS[stage.name] ?? stage.name.replace(/_/g, " ")}
                </span>
                <span className="font-mono text-[9px] text-ink-3">
                  {stage.duration_ms !== null && stage.duration_ms !== undefined ? `${stage.duration_ms.toFixed(0)} ms` : "—"}
                </span>
              </button>
              {index < stages.length - 1 && (
                <span className="relative h-px w-3 shrink-0 bg-line-2" aria-hidden>
                  {complete && (
                    <motion.span
                      className="absolute inset-0 bg-cyan/70"
                      initial={reduceMotion ? false : { scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ duration: 0.3, delay: index * 0.04 }}
                      style={{ transformOrigin: "left" }}
                    />
                  )}
                </span>
              )}
            </div>
          );
        })}
      </div>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key={open.name}
            initial={reduceMotion ? false : { opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden border-t border-line/60"
          >
            <div className="px-4 py-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="label">{LABELS[open.name] ?? open.name} · observable output</span>
                <button
                  type="button"
                  onClick={() => setOpenStage(null)}
                  className="text-2xs uppercase tracking-[0.1em] text-ink-3 hover:text-ink"
                >
                  close
                </button>
              </div>
              <StageOutput stage={open} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function StageOutput({ stage }: { stage: PipelineStage }) {
  const metrics = stage.metrics ?? {};
  const entries = Object.entries(metrics).filter(([key]) => !["embedding", "note"].includes(key));
  if (entries.length === 0) {
    return <p className="text-2xs text-ink-3">no measurable output recorded for this stage.</p>;
  }
  return (
    <div className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-baseline justify-between gap-4 border-b border-line/40 pb-1">
          <span className="truncate text-2xs uppercase tracking-[0.08em] text-ink-3">{key.replace(/_/g, " ")}</span>
          <span className="max-w-[60%] truncate text-right font-mono text-2xs text-ink-2">
            {typeof value === "object" && value !== null ? JSON.stringify(value) : String(value)}
          </span>
        </div>
      ))}
      {typeof metrics.note === "string" && <p className="col-span-full pt-1 text-2xs leading-relaxed text-ink-3">{metrics.note}</p>}
    </div>
  );
}
