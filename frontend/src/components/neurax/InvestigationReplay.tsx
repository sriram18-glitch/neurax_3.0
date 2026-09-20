import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronLeft, ChevronRight, Pause, Play, ScanSearch } from "lucide-react";
import { useEffect, useState } from "react";

import type { InvestigationRecord } from "../../types/api";
import { EvidenceBadge } from "./EvidenceBadge";

const STATUS_TONE: Record<string, string> = {
  COMPLETE: "border-ok/40 text-ok",
  REVIEW: "border-warn/40 text-warn",
  DATA_GAP: "border-line-2 text-ink-3",
  AWAITING_INPUT: "border-warn/40 text-warn",
  FAILED: "border-bad/40 text-bad",
  PARTIAL: "border-cyan/40 text-cyan",
};

/** Replay a stored investigation stage by stage, using the real recorded data. */
export function InvestigationReplay({
  record,
  onOpenInspection,
}: {
  record: InvestigationRecord;
  onOpenInspection?: (inspectionId: string) => void;
}) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const reduceMotion = useReducedMotion();
  const stage = record.stages[Math.min(index, record.stages.length - 1)];

  useEffect(() => {
    setIndex(0);
    setPlaying(false);
  }, [record.investigation_id]);

  useEffect(() => {
    if (!playing) return;
    if (index >= record.stages.length - 1) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => setIndex((current) => current + 1), reduceMotion ? 120 : 900);
    return () => window.clearTimeout(timer);
  }, [playing, index, record.stages.length, reduceMotion]);

  return (
    <div className="flex flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line/60 px-4 py-2.5">
        <button type="button" className="btn-ghost !px-2 !py-1" onClick={() => setIndex((current) => Math.max(0, current - 1))} disabled={index === 0} aria-label="Previous stage">
          <ChevronLeft size={12} aria-hidden />
        </button>
        <button
          type="button"
          className={`btn !px-3 !py-1 ${playing ? "border-warn/50 bg-warn/10 text-warn" : "btn-primary"}`}
          onClick={() => setPlaying((current) => !current)}
        >
          {playing ? <Pause size={12} aria-hidden /> : <Play size={12} aria-hidden />}
          {playing ? "Pause" : index >= record.stages.length - 1 ? "Replay" : "Play investigation"}
        </button>
        <button
          type="button"
          className="btn-ghost !px-2 !py-1"
          onClick={() => setIndex((current) => Math.min(record.stages.length - 1, current + 1))}
          disabled={index >= record.stages.length - 1}
          aria-label="Next stage"
        >
          <ChevronRight size={12} aria-hidden />
        </button>

        <div className="flex flex-1 items-center gap-1" role="progressbar" aria-valuenow={index + 1} aria-valuemin={1} aria-valuemax={record.stages.length}>
          {record.stages.map((entry, entryIndex) => (
            <button
              key={entry.id}
              type="button"
              onClick={() => setIndex(entryIndex)}
              title={entry.label}
              className={`h-1 flex-1 transition-colors ${entryIndex <= index ? "bg-cyan" : "bg-line"}`}
              aria-label={`Stage ${entryIndex + 1}: ${entry.label}`}
            />
          ))}
        </div>

        <span className="font-mono text-2xs text-ink-3">
          {index + 1}/{record.stages.length}
        </span>
        <button
          type="button"
          className="btn-ghost !px-2 !py-1"
          onClick={() => {
            if (record.inspection_id) onOpenInspection?.(record.inspection_id);
          }}
          disabled={!record.inspection_id || !onOpenInspection}
        >
          <ScanSearch size={11} aria-hidden />
          Open inspection
        </button>
      </div>

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={stage.id}
          initial={reduceMotion ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduceMotion ? undefined : { opacity: 0, y: -6 }}
          transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          className="flex flex-col gap-2 px-4 py-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-ink">{stage.label}</span>
            <span className={`chip ${STATUS_TONE[stage.status] ?? "border-line text-ink-3"}`}>{stage.status.replace(/_/g, " ")}</span>
            <EvidenceBadge status={stage.epistemic} />
            {stage.duration_ms !== null && <span className="ml-auto font-mono text-2xs text-ink-3">{stage.duration_ms.toFixed(1)} ms</span>}
          </div>
          <p className="text-2xs leading-relaxed text-ink-2">{stage.summary}</p>
          {stage.detail && <p className="text-2xs leading-relaxed text-ink-3">{stage.detail}</p>}
          {stage.payload && (
            <div className="grid gap-x-6 gap-y-1 border-t border-line/40 pt-2 sm:grid-cols-2">
              {Object.entries(stage.payload)
                .filter(([, value]) => value !== null && value !== undefined && typeof value !== "object")
                .slice(0, 8)
                .map(([key, value]) => (
                  <div key={key} className="flex items-baseline justify-between gap-3 border-b border-line/30 pb-1">
                    <span className="truncate text-2xs uppercase tracking-[0.06em] text-ink-3">{key.replace(/_/g, " ")}</span>
                    <span className="max-w-[60%] truncate text-right font-mono text-2xs text-ink-2">{String(value)}</span>
                  </div>
                ))}
            </div>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
