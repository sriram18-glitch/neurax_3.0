import { motion, useReducedMotion } from "framer-motion";
import { useMemo, useState } from "react";
import { AlertTriangle, Search } from "lucide-react";

import { API_BASE } from "../../api/client";
import { useSession } from "../../session/SessionContext";
import type { BatchRecord, BatchResult } from "../../types/api";
import { AnimatedNumber, HudPanel } from "./Motion";
import { EvidenceBadge } from "./EvidenceBadge";

const DECISION_TONE: Record<string, string> = {
  PASS: "text-ok",
  DEFECT: "text-bad",
  REVIEW: "text-warn",
};

const DECISION_CHIP: Record<string, string> = {
  PASS: "border-ok/40",
  DEFECT: "border-bad/40",
  REVIEW: "border-warn/50 bg-warn/10",
};

type Filter = "ALL" | "PASS" | "DEFECT" | "REVIEW" | "NOVEL" | "LOW CONFIDENCE";

/** Batch results: dashboard, per-image confidence, gallery with filters. */
export function BatchGallery({ batch }: { batch: BatchRecord }) {
  const { loadInspection } = useSession();
  const [filter, setFilter] = useState<Filter>("ALL");
  const [query, setQuery] = useState("");
  const reduceMotion = useReducedMotion();

  const filtered = useMemo(() => {
    return batch.results.filter((result) => {
      if (query && !(result.filename ?? "").toLowerCase().includes(query.toLowerCase())) return false;
      switch (filter) {
        case "PASS":
          return result.decision === "PASS";
        case "DEFECT":
          return result.decision === "DEFECT";
        case "REVIEW":
          return result.decision === "REVIEW";
        case "NOVEL":
          return result.novelty_status === "HIGH";
        case "LOW CONFIDENCE":
          return result.confidence < 0.7;
        default:
          return true;
      }
    });
  }, [batch.results, filter, query]);

  const quality = batch.quality;

  return (
    <div className="flex flex-col gap-3">
      <HudPanel
        title="Dataset inspection complete"
        subtitle={`${batch.summary.valid} inspected · ${batch.duration_s?.toFixed(1) ?? "—"} s · average confidence ${
          batch.avg_confidence !== null ? (batch.avg_confidence * 100).toFixed(1) + "%" : "—"
        }`}
      >
        <div className="grid grid-cols-3 gap-px bg-line/40">
          {(["PASS", "DEFECT", "REVIEW"] as const).map((decision) => (
            <div key={decision} className="flex flex-col items-center gap-0.5 bg-panel/70 py-3">
              <AnimatedNumber value={batch.decisions[decision]} className={`font-mono text-2xl ${DECISION_TONE[decision]}`} />
              <span className="text-[9px] uppercase tracking-[0.12em] text-ink-3">{decision}</span>
            </div>
          ))}
        </div>

        {quality ? (
          <div className="grid gap-x-6 gap-y-2 px-4 py-3 sm:grid-cols-2">
            <div className="grid grid-cols-2 gap-px border border-line/60 bg-line/40">
              <QualityStat label="false accept" value={quality.false_accept_rate} />
              <QualityStat label="false reject" value={quality.false_reject_rate} />
              <QualityStat label="precision" value={quality.precision} />
              <QualityStat label="recall" value={quality.recall} />
              <QualityStat label="F1" value={quality.f1} />
              <QualityStat label="review rate" value={quality.review_rate} />
            </div>
            <div>
              <p className="label mb-1">confusion (defect = positive)</p>
              <p className="font-mono text-2xs text-ink-2">
                TP {quality.tp} · TN {quality.tn} · FP {quality.fp} · FN {quality.fn}
              </p>
              <p className="mt-1 text-2xs leading-relaxed text-ink-3">{quality.basis} · {quality.note}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <EvidenceBadge status="OBSERVED" />
                <span className="chip border-line-2 text-ink-3">ground truth: class folders</span>
              </div>
            </div>
          </div>
        ) : (
          <p className="px-4 py-3 text-2xs leading-relaxed text-ink-3">
            Decision quality (FAR / FRR / precision / recall / F1) requires ground-truth labels — add images inside class
            folders to measure it. {batch.summary.labels_note}
          </p>
        )}

        {batch.review_queue > 0 && (
          <p className="flex items-center gap-2 border-t border-warn/40 bg-warn/5 px-4 py-2 text-2xs text-warn">
            <AlertTriangle size={12} aria-hidden />
            {batch.review_queue} inspection(s) require human review — open the review queue.
          </p>
        )}
      </HudPanel>

      <HudPanel title="Inspection gallery" subtitle="every image has its own result — click to open the full inspection">
        <div className="flex flex-wrap items-center gap-2 border-b border-line/60 px-4 py-2.5">
          {(["ALL", "PASS", "DEFECT", "REVIEW", "NOVEL", "LOW CONFIDENCE"] as Filter[]).map((candidate) => (
            <button
              key={candidate}
              type="button"
              onClick={() => setFilter(candidate)}
              aria-pressed={filter === candidate}
              className={`chip ${filter === candidate ? "border-cyan/50 bg-cyan/10 text-cyan" : "border-line text-ink-3 hover:text-ink-2"}`}
            >
              {candidate}
            </button>
          ))}
          <label className="ml-auto flex items-center gap-1.5 text-2xs text-ink-3">
            <Search size={11} aria-hidden />
            <input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="filename…"
              className="w-32 border border-line bg-bg px-2 py-1 font-mono text-2xs text-ink focus:border-cyan"
              aria-label="Search by filename"
            />
          </label>
        </div>

        {filtered.length === 0 ? (
          <p className="px-4 py-4 text-2xs text-ink-3">No results match this filter.</p>
        ) : (
          <ul className="grid grid-cols-2 gap-2 px-4 py-3 sm:grid-cols-3 lg:grid-cols-4">
            {filtered.map((result, index) => (
              <GalleryCard key={result.inspection_id} result={result} onOpen={() => void loadInspection(result.inspection_id)} index={index} reduceMotion={Boolean(reduceMotion)} />
            ))}
          </ul>
        )}
      </HudPanel>
    </div>
  );
}

function GalleryCard({
  result,
  onOpen,
  index,
  reduceMotion,
}: {
  result: BatchResult;
  onOpen: () => void;
  index: number;
  reduceMotion: boolean;
}) {
  return (
    <li>
      <motion.button
        type="button"
        onClick={onOpen}
        initial={reduceMotion ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: Math.min(index * 0.03, 0.6) }}
        className={`flex w-full flex-col border bg-bg-2/60 text-left transition-colors hover:border-cyan/50 ${DECISION_CHIP[result.decision] ?? "border-line/60"}`}
      >
        <div className="relative border-b border-line/40 bg-black/40">
          <img
            src={`${API_BASE}/api/vision/inspect/${result.inspection_id}/image`}
            alt={result.filename ?? result.inspection_id}
            className="h-28 w-full object-contain"
            loading="lazy"
          />
          {result.decision === "REVIEW" && (
            <span className="absolute left-1 top-1 flex items-center gap-1 border border-warn/50 bg-warn/10 px-1 py-0.5 font-mono text-[9px] text-warn">
              <AlertTriangle size={8} aria-hidden />
              REVIEW
            </span>
          )}
          {result.novelty_status === "HIGH" && (
            <span className="absolute right-1 top-1 border border-novel/50 bg-bg/80 px-1 py-0.5 font-mono text-[9px] text-novel">
              NOVEL
            </span>
          )}
        </div>
        <div className="flex flex-col gap-1 p-2">
          <span className="truncate font-mono text-[9px] text-ink-3">{result.filename}</span>
          <span className={`font-mono text-xs ${DECISION_TONE[result.decision] ?? "text-ink-2"}`}>{result.decision}</span>
          <span className="flex items-center gap-1.5">
            <span className="h-1 flex-1 bg-line/50">
              <span
                className={`block h-full ${result.decision === "PASS" ? "bg-ok/80" : result.decision === "DEFECT" ? "bg-bad/80" : "bg-warn/80"}`}
                style={{ width: `${result.confidence * 100}%` }}
              />
            </span>
            <span className="w-11 shrink-0 text-right font-mono text-[9px] text-ink-2">{(result.confidence * 100).toFixed(1)}%</span>
          </span>
          {result.class_folder && (
            <span className="truncate font-mono text-[9px] text-ink-3">{result.class_folder}</span>
          )}
        </div>
      </motion.button>
    </li>
  );
}

function QualityStat({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2">
      <span className="label">{label}</span>
      <AnimatedNumber value={value !== null ? value * 100 : null} digits={1} suffix="%" className="text-sm text-ink" />
    </div>
  );
}