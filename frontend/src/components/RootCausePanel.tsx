import { useEffect, useState } from "react";
import { Play, RefreshCw } from "lucide-react";

import { api } from "../api/client";
import { useSession } from "../session/SessionContext";
import type { RootCauseFinding } from "../types/api";
import { NotAvailable, Panel, formatNumber, statusIcon, statusTone } from "./ui/Primitives";

export function RootCausePanel({ onInspect }: { onInspect: (finding: RootCauseFinding) => void }) {
  const { datasetId, rootCause, runRootCause, busy } = useSession();
  const [target, setTarget] = useState("");
  const [direction, setDirection] = useState("low");
  const [targets, setTargets] = useState<Array<{ target: string; input: string; mode: string }>>([]);

  useEffect(() => {
    let cancelled = false;
    if (!datasetId) {
      setTargets([]);
      return;
    }
    api
      .getRootCauseTargets(datasetId)
      .then((result) => {
        if (cancelled) return;
        setTargets(result.targets.map((entry) => ({ target: entry.target, input: entry.input, mode: entry.mode })));
        setTarget((current) => current || result.targets[0]?.target || "");
      })
      .catch(() => {
        if (!cancelled) setTargets([]);
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  const run = () => {
    if (target) void runRootCause(target, direction, 0.1);
  };

  return (
    <Panel
      title="Root-cause analysis"
      subtitle={rootCause ? `engine v${rootCause.engine_version} · ${rootCause.total_duration_s}s` : "Not yet run"}
      actions={
        <button type="button" className="btn-ghost" onClick={run} disabled={Boolean(busy) || !target}>
          {busy?.includes("root-cause") ? (
            <RefreshCw size={11} className="animate-spin" aria-hidden />
          ) : (
            <Play size={11} aria-hidden />
          )}
          Analyze
        </button>
      }
    >
      <div className="flex flex-wrap items-end gap-3 border-b border-line px-4 py-3">
        <label className="flex flex-col gap-1">
          <span className="label">Target</span>
          <select
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            className="border border-line bg-bg px-2 py-1.5 font-mono text-xs text-ink focus:border-cyan"
          >
            {targets.length === 0 && <option value="">no targets available</option>}
            {targets.map((entry) => (
              <option key={`${entry.input}-${entry.target}`} value={entry.target}>
                {entry.target} ({entry.mode})
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">Event</span>
          <select
            value={direction}
            onChange={(event) => setDirection(event.target.value)}
            className="border border-line bg-bg px-2 py-1.5 font-mono text-xs text-ink focus:border-cyan"
          >
            <option value="low">low tail (10%)</option>
            <option value="high">high tail (10%)</option>
          </select>
        </label>
      </div>

      {!rootCause ? (
        <div className="px-4 py-4">
          <NotAvailable reason="No root-cause analysis has been run for this dataset yet. Select a target and run the analysis." />
        </div>
      ) : (
        <div className="max-h-[420px] overflow-y-auto">
          <div className="border-b border-line px-4 py-2 text-2xs text-ink-3">
            Event: <span className="font-mono text-ink-2">{rootCause.event.definition}</span> ·{" "}
            {rootCause.event.event_rows.toLocaleString()} of {rootCause.target.rows.toLocaleString()} rows
          </div>
          <ul className="divide-y divide-line">
            {rootCause.ranked_findings.slice(0, 12).map((finding) => (
              <li key={finding.factor}>
                <button
                  type="button"
                  onClick={() => onInspect(finding)}
                  className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-panel-2/50"
                >
                  <span className="mt-0.5 font-mono text-2xs text-ink-3">#{finding.rank}</span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-xs font-medium text-ink">{finding.factor}</span>
                      {finding.station && <span className="chip border-line text-ink-3">{finding.station}</span>}
                      <span className={`chip ${statusTone(finding.association_status)}`}>
                        {statusIcon(finding.association_status)}
                        {finding.association_status.replace(/_/g, " ")}
                      </span>
                    </span>
                    <span className="mt-1 block truncate text-2xs text-ink-2">{finding.explanation}</span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="block font-mono text-sm text-ink">
                      {finding.evidence_score !== null ? formatNumber(finding.evidence_score, 1) : "—"}
                    </span>
                    <span className="label">score</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <p className="border-t border-line px-4 py-2 text-2xs text-ink-3">
            Association does not establish causation. Scores combine correlation, mutual information, group
            difference, temporal and anomaly evidence with fixed documented weights.
          </p>
        </div>
      )}
    </Panel>
  );
}
