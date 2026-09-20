import { AlertTriangle, Check, ChevronUp, Eye } from "lucide-react";
import { useState } from "react";

import { API_BASE } from "../../api/client";
import { useSession } from "../../session/SessionContext";
import { AnimatedNumber } from "./Motion";

/**
 * Human review queue: AI escalates uncertain decisions, humans decide.
 * The human decision is stored separately; the AI result is never overwritten.
 */
export function ReviewQueue({ onOpenInspection }: { onOpenInspection?: (inspectionId: string) => void }) {
  const { reviewQueue, reviewBusy, reviewAction, loadInspection } = useSession();
  const [openId, setOpenId] = useState<string | null>(null);

  if (reviewQueue.length === 0) {
    return (
      <p className="px-4 py-3 text-2xs leading-relaxed text-ink-3">
        Review queue empty. When the AI is uncertain — low confidence, novel or anomalous samples — the decision moves to
        REVIEW and appears here for a human decision.
      </p>
    );
  }

  const open = reviewQueue.find((entry) => entry.inspection_id === openId) ?? null;

  return (
    <div className="flex flex-col">
      <p className="flex items-center gap-2 border-b border-warn/40 bg-warn/5 px-4 py-2 text-2xs font-semibold uppercase tracking-[0.12em] text-warn">
        <AlertTriangle size={12} aria-hidden />
        {reviewQueue.length} inspection(s) require human review
      </p>
      <ul className="max-h-72 overflow-y-auto">
        {reviewQueue.slice(0, 30).map((entry) => (
          <li key={entry.inspection_id} className="border-b border-line/40 last:border-b-0">
            <button
              type="button"
              onClick={() => setOpenId((current) => (current === entry.inspection_id ? null : entry.inspection_id))}
              aria-expanded={openId === entry.inspection_id}
              className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-panel-2/40"
            >
              <span className="h-8 w-8 shrink-0 border border-line-2 bg-black/40">
                <img src={`${API_BASE}/api/vision/inspect/${entry.inspection_id}/image`} alt="" className="h-full w-full object-contain" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-mono text-2xs text-ink-2">{entry.filename ?? entry.inspection_id}</span>
                <span className="block text-[9px] text-ink-3">
                  {entry.predicted_class} · {(entry.confidence ?? 0) * 100 === 0 ? "—" : `${((entry.confidence ?? 0) * 100).toFixed(1)}%`} · novelty {entry.novelty_status}
                </span>
              </span>
              <ChevronUp size={12} className={`text-ink-3 transition-transform ${openId === entry.inspection_id ? "" : "rotate-180"}`} aria-hidden />
            </button>
          </li>
        ))}
      </ul>

      {open && (
        <div className="border-t border-line/60 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-2xs text-warn">AI: REVIEW</span>
            <span className="font-mono text-2xs text-ink-3">
              confidence {(open.confidence ?? 0) * 100 === 0 ? "—" : `${((open.confidence ?? 0) * 100).toFixed(1)}%`}
            </span>
            <span className="ml-auto flex items-center gap-2">
              <button
                type="button"
                className="btn-ghost !px-2 !py-1"
                onClick={() => {
                  if (onOpenInspection) onOpenInspection(open.inspection_id);
                  else void loadInspection(open.inspection_id);
                }}
              >
                <Eye size={11} aria-hidden />
                Open inspection
              </button>
            </span>
          </div>
          <div className="mt-2 flex flex-col gap-1.5">
            {open.review_reasons.length > 0 ? (
              open.review_reasons.map((reason) => (
                <p key={reason} className="flex items-start gap-2 text-2xs leading-relaxed text-ink-2">
                  <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-warn" aria-hidden />
                  {reason}
                </p>
              ))
            ) : (
              <p className="text-2xs leading-relaxed text-ink-2">{open.review_reason ?? "no reason recorded"}</p>
            )}
            <p className="text-2xs text-ink-3">
              anomaly {open.anomaly_score !== null ? open.anomaly_score.toFixed(3) : "—"} · novelty{" "}
              {open.novelty_score !== null ? open.novelty_score.toFixed(3) : "—"} · localization{" "}
              {open.localization ? "available" : "not available"}
            </p>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line/40 pt-3">
            <span className="label mr-1">human decision</span>
            <button
              type="button"
              className="btn border-ok/50 bg-ok/10 text-ok !px-3 !py-1.5"
              onClick={() => void reviewAction(open.inspection_id, "confirm_defect")}
              disabled={reviewBusy}
            >
              <Check size={11} aria-hidden />
              Confirm defect
            </button>
            <button
              type="button"
              className="btn border-ok/50 bg-ok/10 text-ok !px-3 !py-1.5"
              onClick={() => void reviewAction(open.inspection_id, "mark_pass")}
              disabled={reviewBusy}
            >
              Mark pass
            </button>
            <button
              type="button"
              className="btn border-warn/50 bg-warn/10 text-warn !px-3 !py-1.5"
              onClick={() => void reviewAction(open.inspection_id, "escalate")}
              disabled={reviewBusy}
            >
              Escalate
            </button>
            <p className="text-2xs leading-relaxed text-ink-3">
              The AI decision and evidence are preserved; the human decision is stored separately.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

/** Review statistics: auto-resolved vs human-reviewed, all real values. */
export function ReviewStatsPanel() {
  const { reviewStats } = useSession();
  if (!reviewStats) {
    return <p className="px-4 py-3 text-2xs text-ink-3">No review statistics yet.</p>;
  }
  if (reviewStats.total === 0) {
    return <p className="px-4 py-3 text-2xs text-ink-3">No inspections recorded yet — statistics appear after the first run.</p>;
  }
  const tiles = [
    { label: "auto resolved", value: reviewStats.auto_resolved_rate, tone: "text-ok" },
    { label: "human review", value: reviewStats.human_review_rate, tone: "text-warn" },
    { label: "pending review", value: reviewStats.pending_review_rate, tone: "text-warn" },
  ];
  return (
    <div className="flex flex-col gap-3 px-4 py-3">
      <div className="grid grid-cols-3 gap-px bg-line/40">
        {tiles.map((tile) => (
          <div key={tile.label} className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2.5">
            <span className="label">{tile.label}</span>
            <AnimatedNumber value={tile.value !== null ? tile.value * 100 : null} digits={1} suffix="%" className={`text-lg ${tile.tone}`} />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-px bg-line/40">
        {(["PASS", "DEFECT", "REVIEW"] as const).map((decision) => (
          <div key={decision} className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2">
            <span className="label">{decision}</span>
            <span className="font-mono text-sm text-ink">
              {reviewStats.distribution[decision]} <span className="text-ink-3">({((reviewStats.distribution_rates[decision] ?? 0) * 100).toFixed(1)}%)</span>
            </span>
          </div>
        ))}
      </div>
      <p className="text-2xs leading-relaxed text-ink-3">
        {reviewStats.note} Average confidence:{" "}
        {reviewStats.avg_confidence !== null ? `${(reviewStats.avg_confidence * 100).toFixed(1)}%` : "—"}.
      </p>
    </div>
  );
}