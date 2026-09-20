import { motion, useReducedMotion } from "framer-motion";

import type { BottleneckAnalysis } from "../../types/api";
import { DataGap } from "./DataGap";
import { EvidenceBadge } from "./EvidenceBadge";

const COMPONENT_LABELS: Record<string, string> = {
  utilization_pressure: "utilization",
  queue_pressure: "queue",
  cycle_time_pressure: "cycle time",
  throughput_constraint: "throughput constraint",
  root_cause_evidence: "root-cause evidence",
  anomaly_evidence: "anomaly evidence",
};

/** Bottleneck explanation: why this station, with the real component scores. */
export function BottleneckVisualizer({ bottleneck }: { bottleneck: BottleneckAnalysis | null }) {
  const reduceMotion = useReducedMotion();
  if (!bottleneck) {
    return (
      <DataGap
        title="No bottleneck analysis"
        reason="Run the bottleneck analysis to rank stations by utilization, queue, cycle time, throughput, root-cause and anomaly evidence."
      />
    );
  }
  const candidate = bottleneck.candidate_bottleneck;
  const finding = bottleneck.station_rankings.find((entry) => entry.station === candidate.station) ?? null;
  const components = finding?.score_components ?? {};
  const available = Object.entries(components).filter(([, value]) => value !== null) as Array<[string, number]>;
  const missing = Object.entries(components).filter(([, value]) => value === null).map(([key]) => key);

  return (
    <div className="flex flex-col gap-3 px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <p className="label">candidate constraint</p>
          <p className="font-mono text-lg text-ink">{candidate.station ?? "none identified"}</p>
        </div>
        {candidate.evidence_score !== null && (
          <div>
            <p className="label">evidence score</p>
            <p className="font-mono text-lg text-ink">{candidate.evidence_score.toFixed(1)}</p>
          </div>
        )}
        {candidate.evidence_quality && (
          <span className="chip border-line-2 text-ink-2">{candidate.evidence_quality.label.replace(/_/g, " ")}</span>
        )}
        <span className="ml-auto">
          <EvidenceBadge status="EVIDENCE-BASED HYPOTHESIS" />
        </span>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {available.map(([key, value], index) => (
          <div key={key} className="flex items-center gap-3">
            <span className="w-32 shrink-0 text-2xs uppercase tracking-[0.08em] text-ink-3">
              {COMPONENT_LABELS[key] ?? key.replace(/_/g, " ")}
            </span>
            <span className="relative h-2 flex-1 bg-line/50">
              <motion.span
                className="absolute inset-y-0 left-0 bg-cyan"
                initial={reduceMotion ? false : { width: 0 }}
                animate={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
                transition={{ duration: 0.6, delay: index * 0.05, ease: [0.22, 1, 0.36, 1] }}
              />
            </span>
            <span className="w-10 shrink-0 text-right font-mono text-2xs text-ink-3">{value.toFixed(2)}</span>
          </div>
        ))}
      </div>

      {candidate.why.length > 0 && (
        <ul className="flex flex-col gap-1 border-t border-line/60 pt-2">
          {candidate.why.slice(0, 5).map((reason) => (
            <li key={reason} className="font-mono text-2xs text-ink-2">
              {reason}
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line/60 pt-2 text-2xs text-ink-3">
        <span>
          {available.length} supporting signal(s) · {bottleneck.stations_analyzed} station(s) analyzed
        </span>
        {missing.length > 0 && <span className="text-warn">not available from dataset: {missing.map((key) => COMPONENT_LABELS[key] ?? key).join(", ")}</span>}
      </div>
      <p className="text-2xs leading-relaxed text-ink-3">
        Bottleneck identification is an evidence-based hypothesis, not a proven constraint. Highest utilization alone is never
        sufficient.
      </p>
    </div>
  );
}
