import { useMemo } from "react";

import { useSession } from "../../session/SessionContext";
import { EvidenceBadge } from "./EvidenceBadge";

const TYPE_LABEL: Record<string, string> = {
  inspection_completed: "Inspection completed",
  defect_detected: "Defect detected",
  review_required: "Review required",
  investigation_triggered: "Investigation triggered",
  process_correlation_complete: "Process correlation",
  process_correlation_data_gap: "Process correlation",
  root_cause_complete: "Root-cause analysis complete",
  root_cause_data_gap: "Root-cause analysis",
  root_cause_failed: "Root-cause analysis",
  bottleneck_complete: "Bottleneck candidate identified",
  bottleneck_data_gap: "Bottleneck analysis",
  impact_complete: "Impact computed",
  impact_awaiting_input: "Impact",
  what_if_complete: "Scenario recorded",
  what_if_awaiting_input: "What-if",
  recommendation_complete: "Recommendation generated",
  recommendation_data_gap: "Recommendation",
};

function timeOf(iso: string | null | undefined): string {
  if (!iso) return "--:--:--";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return date.toLocaleTimeString("en-GB", { hour12: false });
}

/** Industrial event feed: business events, never developer diagnostics. */
export function IndustrialEventFeed({ limit = 14 }: { limit?: number }) {
  const { stream, investigation, investigations } = useSession();

  const events = useMemo(() => {
    const collected: Array<{ at: string; label: string; message: string; epistemic: string }> = [];
    for (const entry of stream?.history ?? []) {
      collected.push({
        at: entry.at,
        label: entry.decision === "DEFECT" ? "Defect detected" : entry.decision === "REVIEW" ? "Review required" : "Inspection completed",
        message: `${entry.filename ?? entry.inspection_id} — ${entry.predicted_class} (${entry.decision})`,
        epistemic: "MODEL OUTPUT",
      });
    }
    if (investigation?.events) {
      for (const event of investigation.events) {
        collected.push({
          at: event.at,
          label: TYPE_LABEL[event.type] ?? event.type.replace(/_/g, " "),
          message: event.message,
          epistemic: event.epistemic,
        });
      }
    } else {
      for (const summary of investigations.slice(0, 6)) {
        collected.push({
          at: summary.generated_at,
          label: "Investigation recorded",
          message: `${summary.filename ?? summary.inspection_id} — ${summary.status.replace(/_/g, " ").toLowerCase()}`,
          epistemic: "OBSERVED",
        });
      }
    }
    return collected
      .filter((event) => Boolean(event.at))
      .sort((a, b) => (a.at < b.at ? 1 : -1))
      .slice(0, limit);
  }, [stream, investigation, investigations, limit]);

  if (events.length === 0) {
    return (
      <p className="px-4 py-3 text-2xs leading-relaxed text-ink-3">
        No industrial events yet. Start the automated inspection stream — every completed inspection, defect decision and
        investigation stage appears here.
      </p>
    );
  }

  return (
    <ol className="flex flex-col">
      {events.map((event, index) => (
        <li key={`${event.at}-${index}`} className="flex gap-3 border-b border-line/30 px-4 py-2 last:border-b-0">
          <span className="shrink-0 font-mono text-[9px] text-ink-3">{timeOf(event.at)}</span>
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-2">
              <span className="text-2xs font-medium text-ink-2">{event.label}</span>
              <EvidenceBadge status={event.epistemic} />
            </span>
            <span className="mt-0.5 block truncate text-[9px] text-ink-3">{event.message}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}
