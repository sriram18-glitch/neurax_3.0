import { ArrowRight } from "lucide-react";

import { useSession } from "../../session/SessionContext";
import { AnimatedNumber } from "./Motion";
import { EvidenceBadge } from "./EvidenceBadge";

/**
 * Impact flow: observed production → user assumptions → calculated impact.
 * If assumptions are missing, the chain shows exactly what is required.
 */
export function ImpactFlow() {
  const { baseline, assumptions, scenario, bottleneck } = useSession();

  if (!baseline) {
    return (
      <div className="flex flex-col gap-3 px-4 py-3">
        <div className="flex flex-wrap items-stretch gap-2">
          {["observed throughput", "user assumptions", "calculated impact"].map((step, index) => (
            <div key={step} className="flex items-stretch gap-2">
              <div className="flex min-w-[150px] flex-col justify-center gap-1 border border-dashed border-line px-3 py-2.5">
                <span className="label">{step}</span>
                <span className="font-mono text-2xs text-ink-3">
                  {index === 0 ? "requires a bottleneck analysis" : index === 1 ? "requires user input" : "not available"}
                </span>
              </div>
              {index < 2 && (
                <span className="flex items-center text-ink-3" aria-hidden>
                  <ArrowRight size={14} />
                </span>
              )}
            </div>
          ))}
        </div>
        <p className="text-2xs leading-relaxed text-ink-3">
          The process datasets contain no economic columns. Supply the assumptions to unlock the calculation — no value is
          invented by the system.
        </p>
      </div>
    );
  }

  const { throughput_per_hour, units_per_day, daily_contribution, monthly_contribution } = baseline.baseline;
  const steps = [
    { label: "observed throughput", value: throughput_per_hour.value, suffix: "units/hour", digits: 2, status: "OBSERVED", formula: throughput_per_hour.source },
    { label: "units per day", value: units_per_day.value, suffix: "units/day", digits: 0, status: units_per_day.status, formula: units_per_day.formula },
    { label: "daily contribution", value: daily_contribution.value, suffix: baseline.currency ?? "", digits: 0, status: daily_contribution.status, formula: daily_contribution.formula },
    { label: "monthly contribution", value: monthly_contribution.value, suffix: baseline.currency ?? "", digits: 0, status: monthly_contribution.status, formula: monthly_contribution.formula },
  ];
  const netImpact = scenario?.economic_output.net_daily_impact;

  return (
    <div className="flex flex-col gap-3 px-4 py-4">
      <div className="flex flex-wrap items-stretch gap-2">
        {steps.map((step, index) => (
          <div key={step.label} className="flex items-stretch gap-2">
            <div className="flex min-w-[150px] flex-col gap-1 border border-line/60 bg-bg-2/50 px-3 py-2.5">
              <span className="label">{step.label}</span>
              <AnimatedNumber
                value={step.value}
                digits={step.digits}
                suffix={step.suffix ? ` ${step.suffix}` : undefined}
                className="text-lg text-ink"
              />
              <EvidenceBadge status={step.status.replace(/_/g, " ")} />
              <span className="mt-1 font-mono text-[9px] leading-relaxed text-ink-3">{step.formula}</span>
            </div>
            {index < steps.length - 1 && (
              <span className="flex items-center text-ink-3" aria-hidden>
                <ArrowRight size={14} />
              </span>
            )}
          </div>
        ))}
      </div>

      {scenario && netImpact && (
        <div className="flex flex-wrap items-center gap-4 border border-warn/30 bg-warn/5 px-4 py-3">
          <div>
            <p className="label">scenario net daily impact</p>
            <AnimatedNumber
              value={netImpact.value}
              digits={0}
              suffix={` ${baseline.currency ?? ""}`}
              className={`text-lg ${(netImpact.value ?? 0) >= 0 ? "text-ok" : "text-bad"}`}
            />
          </div>
          <span className="chip border-warn/40 text-warn">SIMULATION — assumption-based, not a forecast</span>
          <span className="text-2xs text-ink-3">
            cost blocks included: {(netImpact.cost_blocks_included ?? []).join(", ") || "none"} · missing:{" "}
            {(netImpact.cost_blocks_missing ?? []).join(", ") || "none"}
          </span>
        </div>
      )}

      <p className="text-2xs leading-relaxed text-ink-3">
        {baseline.baseline.note}
        {bottleneck?.candidate_bottleneck.station
          ? ` Baseline relates to the candidate constraint ${bottleneck.candidate_bottleneck.station}.`
          : ""}
        {assumptions
          ? ` ${Object.values(assumptions.assumptions).filter((entry) => entry.value !== null).length} user assumption(s) supplied.`
          : ""}
      </p>
    </div>
  );
}
