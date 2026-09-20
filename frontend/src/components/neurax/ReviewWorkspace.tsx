import { motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, Check, Eye, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";

import { API_BASE } from "../../api/client";
import { useSession } from "../../session/SessionContext";
import { AnimatedNumber } from "./Motion";
import { EvidenceBadge } from "./EvidenceBadge";

/**
 * Human review workspace: left = pending items with real thumbnails,
 * right = the selected inspection with the actual image, localization,
 * probabilities, thresholds, explicit reasons and human actions.
 */
export function ReviewWorkspace({ onOpenInspection }: { onOpenInspection?: (inspectionId: string) => void }) {
  const { reviewQueue, reviewStats, reviewBusy, reviewAction, loadInspection, visionStatus } = useSession();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const reduceMotion = useReducedMotion();

  const selected = useMemo(
    () => reviewQueue.find((entry) => entry.inspection_id === selectedId) ?? reviewQueue[0] ?? null,
    [reviewQueue, selectedId],
  );

  const defectClasses = visionStatus?.classes?.filter((name) => name !== visionStatus?.normal_class) ?? [];

  if (reviewQueue.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
        <ShieldAlert size={22} className="text-ok" aria-hidden />
        <p className="text-sm text-ink-2">Review queue empty</p>
        <p className="max-w-md text-2xs leading-relaxed text-ink-3">
          When the AI is uncertain — low confidence, novel or anomalous samples — the automatic decision is blocked and the
          item appears here. {reviewStats && reviewStats.total > 0 ? `Across ${reviewStats.total} inspections, ${(reviewStats.auto_resolved_rate ?? 0) * 100 >= 0 ? ((reviewStats.auto_resolved_rate ?? 0) * 100).toFixed(1) : "—"}% were auto-resolved.` : ""}
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-3 xl:grid-cols-[360px_minmax(0,1fr)]">
      <div className="flex min-w-0 flex-col gap-2">
        <p className="flex items-center gap-2 border border-warn/50 bg-warn/10 px-3 py-2 font-mono text-2xs uppercase tracking-[0.12em] text-warn">
          <AlertTriangle size={12} aria-hidden />
          {reviewQueue.length} inspection(s) require human review
        </p>
        <ul className="flex max-h-[70vh] flex-col gap-2 overflow-y-auto pr-1">
          {reviewQueue.map((entry) => {
            const active = entry.inspection_id === selected?.inspection_id;
            return (
              <li key={entry.inspection_id}>
                <motion.button
                  type="button"
                  onClick={() => setSelectedId(entry.inspection_id)}
                  initial={reduceMotion ? false : { opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`flex w-full gap-3 border px-3 py-2.5 text-left transition-colors ${
                    active ? "border-cyan/60 bg-cyan/5" : "border-line/60 hover:border-cyan/40"
                  }`}
                >
                  <span className="h-14 w-14 shrink-0 border border-line-2 bg-black/40">
                    <img src={`${API_BASE}/api/vision/inspect/${entry.inspection_id}/image`} alt="" className="h-full w-full object-contain" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-mono text-2xs text-ink-2">{entry.filename ?? entry.inspection_id}</span>
                    <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                      <span className="font-mono text-2xs text-warn">REVIEW</span>
                      <span className="text-2xs text-ink-2">{entry.predicted_class}</span>
                    </span>
                    <span className="mt-0.5 block text-[9px] text-ink-3">
                      confidence {(entry.confidence ?? 0) * 100 === 0 ? "—" : `${((entry.confidence ?? 0) * 100).toFixed(1)}%`} · novelty {entry.novelty_status}
                    </span>
                    <span className="mt-0.5 block truncate text-[9px] text-warn">
                      {entry.review_reasons[0] ?? entry.review_reason ?? "uncertain decision"}
                    </span>
                  </span>
                </motion.button>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="min-w-0">
        {selected && (
          <motion.div
            key={selected.inspection_id}
            initial={reduceMotion ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col gap-3"
          >
            <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <div className="relative border border-line-2 bg-black/50 p-2">
                <img
                  src={`${API_BASE}/api/vision/inspect/${selected.inspection_id}/image`}
                  alt="Inspection under review"
                  className="max-h-[46vh] w-full object-contain"
                />
                {selected.localization && (
                  <span className="absolute left-1 top-1 bg-cyan/20 px-1 font-mono text-2xs text-cyan">MODEL-DERIVED REGION</span>
                )}
              </div>
              <div className="flex flex-col gap-2">
                <div className="border border-line/60 bg-bg-2/50 px-3 py-2">
                  <p className="label mb-1">AI decision</p>
                  <div className="flex flex-wrap items-baseline gap-3">
                    <span className="font-mono text-lg text-warn">REVIEW</span>
                    <span className="font-mono text-2xs text-ink-2">predicted: {selected.predicted_class}</span>
                  </div>
                  <p className="mt-1 font-mono text-2xs text-ink-3">
                    confidence <AnimatedNumber value={(selected.confidence ?? 0) * 100} digits={1} suffix="%" />
                  </p>
                </div>

                <div className="border border-warn/40 bg-warn/5 px-3 py-2">
                  <p className="label mb-1.5 text-warn">Why human review?</p>
                  <ul className="flex flex-col gap-1">
                    {(selected.review_reasons.length > 0 ? selected.review_reasons : [selected.review_reason ?? "uncertain decision"]).map((reason) => (
                      <li key={reason} className="flex items-start gap-2 text-2xs leading-relaxed text-ink-2">
                        <Check size={11} className="mt-0.5 shrink-0 text-warn" aria-hidden />
                        {reason}
                      </li>
                    ))}
                    <li className="flex items-start gap-2 text-2xs leading-relaxed text-ink-2">
                      <Check size={11} className="mt-0.5 shrink-0 text-warn" aria-hidden />
                      The model should not make an automatic decision for this sample
                    </li>
                  </ul>
                </div>

                <div className="grid grid-cols-2 gap-px border border-line/60 bg-line/40">
                  <ReviewStat label="anomaly percentile" value={selected.anomaly_score} digits={3} />
                  <ReviewStat label="novelty score" value={selected.novelty_score} digits={3} />
                  <div className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2">
                    <span className="label">novelty status</span>
                    <span className={`font-mono text-sm ${selected.novelty_status === "HIGH" ? "text-novel" : "text-ink"}`}>
                      {selected.novelty_status}
                    </span>
                  </div>
                  <div className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2">
                    <span className="label">localization</span>
                    <span className="font-mono text-sm text-ink">{selected.localization ? "model-derived" : "not available"}</span>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <EvidenceBadge status="MODEL OUTPUT" />
                  <span className="text-2xs text-ink-3">decision thresholds: pass ≥ 0.80 · defect ≥ 0.70 · review gate 0.99</span>
                </div>
              </div>
            </div>

            <div className="border border-line/60 bg-bg-2/40 px-4 py-3">
              <p className="label mb-2">Human decision — stored separately, the AI result is preserved</p>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className="btn border-bad/50 bg-bad/10 text-bad !px-3 !py-1.5"
                  onClick={() => void reviewAction(selected.inspection_id, "confirm_defect")}
                  disabled={reviewBusy}
                >
                  Confirm defect
                </button>
                {defectClasses
                  .filter((name) => name !== selected.predicted_class)
                  .slice(0, 2)
                  .map((name) => (
                    <button
                      key={name}
                      type="button"
                      className="btn-ghost !px-3 !py-1.5"
                      onClick={() => void reviewAction(selected.inspection_id, "confirm_defect", undefined, name)}
                      disabled={reviewBusy}
                    >
                      Confirm {name}
                    </button>
                  ))}
                <button
                  type="button"
                  className="btn border-ok/50 bg-ok/10 text-ok !px-3 !py-1.5"
                  onClick={() => void reviewAction(selected.inspection_id, "mark_pass")}
                  disabled={reviewBusy}
                >
                  Mark pass
                </button>
                <button
                  type="button"
                  className="btn-ghost !px-3 !py-1.5"
                  onClick={() => void reviewAction(selected.inspection_id, "keep_in_review")}
                  disabled={reviewBusy}
                >
                  Keep in review
                </button>
                <button
                  type="button"
                  className="btn border-warn/50 bg-warn/10 text-warn !px-3 !py-1.5"
                  onClick={() => void reviewAction(selected.inspection_id, "escalate")}
                  disabled={reviewBusy}
                >
                  Escalate
                </button>
                <button
                  type="button"
                  className="btn-ghost ml-auto !px-3 !py-1.5"
                  onClick={() => {
                    if (onOpenInspection) onOpenInspection(selected.inspection_id);
                    else void loadInspection(selected.inspection_id);
                  }}
                >
                  <Eye size={11} aria-hidden />
                  Open full inspection
                </button>
              </div>
              <p className="mt-2 text-2xs leading-relaxed text-ink-3">
                Confirming a specific defect class records the class name with the human decision. Keep in review leaves the
                item pending for another operator.
              </p>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}

function ReviewStat({ label, value, digits }: { label: string; value: number | null; digits: number }) {
  return (
    <div className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2">
      <span className="label">{label}</span>
      <AnimatedNumber value={value} digits={digits} className="font-mono text-sm text-ink" />
    </div>
  );
}