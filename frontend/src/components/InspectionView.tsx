import { ArrowRight } from "lucide-react";

import { useSession } from "../session/SessionContext";
import type { OpenEvidence } from "./evidence";
import { InspectionTheater } from "./InspectionTheater";
import { Panel, formatNumber, statusTone } from "./ui/Primitives";

export type { OpenEvidence };

/**
 * INSPECT — the primary experience. The theater streams the real pipeline
 * live; recent inspections below are real stored records.
 */
export function InspectionView({ onOpenEvidence }: { onOpenEvidence: OpenEvidence }) {
  return (
    <div className="flex flex-col gap-3 p-3">
      <InspectionTheater onOpenEvidence={onOpenEvidence} />
      <RecentInspections />
    </div>
  );
}

function RecentInspections() {
  const { inspectionHistory, inspection, loadInspection } = useSession();
  if (inspectionHistory.length === 0) {
    return null;
  }
  return (
    <Panel title="Recent inspections" subtitle={`${inspectionHistory.length} real inspection record(s)`}>
      <div className="flex gap-3 overflow-x-auto px-4 py-3">
        {inspectionHistory.map((entry) => (
          <button
            key={entry.inspection_id}
            type="button"
            onClick={() => void loadInspection(entry.inspection_id)}
            className={`flex w-44 shrink-0 flex-col gap-1.5 border px-3 py-2.5 text-left transition-colors ${
              inspection?.inspection_id === entry.inspection_id ? "border-cyan/50 bg-cyan/5" : "border-line hover:border-line-2"
            }`}
          >
            <span className="flex items-center justify-between gap-2">
              <span className={`chip ${statusTone(entry.decision)}`}>{entry.decision}</span>
              <span className="font-mono text-2xs text-ink-3">{(entry.confidence * 100).toFixed(0)}%</span>
            </span>
            <span className="truncate text-xs text-ink">{entry.predicted_class}</span>
            <span className="truncate text-2xs text-ink-3">{entry.filename ?? entry.inspection_id}</span>
            <span className="flex items-center gap-1 text-2xs text-ink-3">
              anomaly {formatNumber(entry.anomaly_score, 3)}
              <ArrowRight size={9} aria-hidden />
            </span>
          </button>
        ))}
      </div>
    </Panel>
  );
}
