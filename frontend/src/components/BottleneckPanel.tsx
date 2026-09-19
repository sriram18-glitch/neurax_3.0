import { motion, useReducedMotion } from "framer-motion";
import { RefreshCw } from "lucide-react";

import { useSession } from "../session/SessionContext";
import type { BottleneckFinding } from "../types/api";
import { NotAvailable, Panel, formatNumber, statusIcon, statusTone } from "./ui/Primitives";

function toneFor(finding: BottleneckFinding): string {
  if (finding.status === "CANDIDATE_BOTTLENECK") return "border-bad/40 bg-bad/5";
  if (finding.status === "POSSIBLE_CONTRIBUTOR") return "border-warn/30";
  if (finding.status === "INSUFFICIENT_EVIDENCE") return "border-line opacity-70";
  return "border-line";
}

export function BottleneckPanel({ onInspect }: { onInspect: (finding: BottleneckFinding) => void }) {
  const { bottleneck, runBottleneck, busy } = useSession();
  const reduceMotion = useReducedMotion();

  return (
    <Panel
      title="Station constraint ranking"
      subtitle={
        bottleneck
          ? `${bottleneck.stations_analyzed} station(s) · engine v${bottleneck.engine_version} · ${bottleneck.total_duration_s}s`
          : "Not yet analyzed"
      }
      actions={
        <button type="button" className="btn-ghost" onClick={() => void runBottleneck()} disabled={Boolean(busy)}>
          {busy?.includes("bottleneck") ? (
            <RefreshCw size={11} className="animate-spin" aria-hidden />
          ) : (
            <RefreshCw size={11} aria-hidden />
          )}
          Re-run
        </button>
      }
    >
      {!bottleneck ? (
        <div className="px-4 py-4">
          <NotAvailable reason="No bottleneck analysis exists for this dataset yet." />
        </div>
      ) : (
        <div className="max-h-[420px] overflow-y-auto">
          <ul className="divide-y divide-line">
            {bottleneck.station_rankings.map((finding, index) => (
              <motion.li
                key={finding.station}
                initial={reduceMotion ? false : { opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: reduceMotion ? 0 : index * 0.03 }}
              >
                <button
                  type="button"
                  onClick={() => onInspect(finding)}
                  className={`flex w-full items-start gap-3 border-l-2 px-4 py-3 text-left transition-colors hover:bg-panel-2/50 ${toneFor(finding)}`}
                >
                  <span className="mt-0.5 font-mono text-2xs text-ink-3">#{finding.rank}</span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-medium text-ink">{finding.station}</span>
                      <span className={`chip ${statusTone(finding.status)}`}>
                        {statusIcon(finding.status)}
                        {finding.status.replace(/_/g, " ")}
                      </span>
                      <span className={`chip ${statusTone(finding.evidence_quality.label)}`}>
                        {finding.evidence_quality.label.replace(/_/g, " ")}
                      </span>
                    </span>
                    <span className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-0.5 font-mono text-2xs text-ink-2 sm:grid-cols-4">
                      <span>
                        UTIL{" "}
                        {finding.utilization.available ? `${(finding.utilization.mean ?? 0).toFixed(3)}` : "N/A"}
                      </span>
                      <span>
                        QUEUE {finding.queue.available ? `${(finding.queue.mean ?? 0).toFixed(1)}` : "N/A"}
                      </span>
                      <span>
                        CYCLE {finding.cycle_time.available ? `${(finding.cycle_time.mean ?? 0).toFixed(2)}` : "N/A"}
                      </span>
                      <span>COMPONENTS {finding.available_components}/6</span>
                    </span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="block font-mono text-sm text-ink">
                      {finding.evidence_score !== null ? formatNumber(finding.evidence_score, 1) : "—"}
                    </span>
                    <span className="label">evidence</span>
                  </span>
                </button>
              </motion.li>
            ))}
          </ul>
          {bottleneck.candidate_bottleneck.why.length > 0 && (
            <div className="border-t border-line px-4 py-3">
              <p className="label mb-1.5">Why {bottleneck.candidate_bottleneck.station}</p>
              <ul className="flex flex-wrap gap-2">
                {bottleneck.candidate_bottleneck.why.map((reason) => (
                  <li key={reason} className="chip border-line text-ink-2">
                    {reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="border-t border-line px-4 py-2 text-2xs text-ink-3">
            Evidence-based hypothesis, not a proven constraint. Highest utilization alone is never sufficient.
          </p>
        </div>
      )}
    </Panel>
  );
}
