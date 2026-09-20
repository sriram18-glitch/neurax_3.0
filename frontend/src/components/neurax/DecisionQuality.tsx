import { useSession } from "../../session/SessionContext";
import { AnimatedNumber } from "./Motion";

/**
 * Decision quality: measured test-split rates and the real threshold layout.
 * Values come from the trained model's metrics; nothing is hardcoded.
 */
export function DecisionQuality() {
  const { visionStatus } = useSession();
  const metrics = visionStatus?.metrics;
  const thresholds = visionStatus?.thresholds;
  if (!metrics || !thresholds) {
    return (
      <p className="px-4 py-3 text-2xs leading-relaxed text-ink-3">
        No measured decision quality is available — the vision model has not been trained in this environment.
      </p>
    );
  }
  const pass = thresholds.pass_confidence;
  const defect = thresholds.defect_confidence;
  const matrix = metrics.decision_matrix ?? null;
  const columns = metrics.decision_matrix_columns ?? ["PASS", "DEFECT", "REVIEW"];

  return (
    <div className="flex flex-col gap-3 px-4 py-3">
      <div className="grid grid-cols-3 gap-px bg-line/40">
        <div className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2.5">
          <span className="label">false accept</span>
          <AnimatedNumber
            value={metrics.false_accept_rate !== null ? metrics.false_accept_rate * 100 : null}
            digits={1}
            suffix="%"
            className="text-lg text-ink"
          />
          <span className="text-[9px] text-ink-3">defects accepted as PASS</span>
        </div>
        <div className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2.5">
          <span className="label">false reject</span>
          <AnimatedNumber
            value={metrics.false_reject_rate !== null ? metrics.false_reject_rate * 100 : null}
            digits={1}
            suffix="%"
            className="text-lg text-ink"
          />
          <span className="text-[9px] text-ink-3">normal parts rejected</span>
        </div>
        <div className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2.5">
          <span className="label">review rate</span>
          <AnimatedNumber value={metrics.review_rate * 100} digits={1} suffix="%" className="text-lg text-warn" />
          <span className="text-[9px] text-ink-3">sent to human review</span>
        </div>
      </div>

      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="label">decision thresholds</span>
          <span className="font-mono text-2xs text-ink-3">measured on the held-out test split</span>
        </div>
        <div className="relative flex h-8 border border-line/60 bg-bg-2/50 text-[9px] uppercase tracking-[0.1em]">
          <div className="flex items-center justify-center bg-bad/15 text-bad" style={{ width: `${defect * 100}%` }}>
            defect &lt; {defect.toFixed(2)}
          </div>
          <div
            className="flex items-center justify-center bg-warn/10 text-warn"
            style={{ width: `${(pass - defect) * 100}%` }}
          >
            review
          </div>
          <div className="flex flex-1 items-center justify-center bg-ok/15 text-ok">pass ≥ {pass.toFixed(2)}</div>
        </div>
        <p className="mt-1.5 text-2xs leading-relaxed text-ink-3">
          REVIEW is forced when calibrated confidence falls between the gates or the anomaly percentile exceeds{" "}
          {thresholds.anomaly_review_percentile.toFixed(2)} — this is how the system avoids forcing every part into
          PASS/DEFECT.
        </p>
      </div>

      {matrix && (
        <table className="w-full border-collapse text-2xs">
          <thead>
            <tr>
              <th className="border border-line/60 px-2 py-1 text-left font-normal text-ink-3">actual</th>
              {columns.map((column) => (
                <th key={column} className="border border-line/60 px-2 py-1 text-right font-mono font-normal text-ink-3">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row) => (
              <tr key={row.actual}>
                <td className="border border-line/60 px-2 py-1 text-ink-3">{row.actual}</td>
                {columns.map((column) => (
                  <td key={column} className="border border-line/60 px-2 py-1 text-right font-mono text-ink-2">
                    {row.counts[column] ?? 0}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
