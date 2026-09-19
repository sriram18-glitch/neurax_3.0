import { useEffect, useMemo, useState } from "react";
import { FlaskConical } from "lucide-react";

import { useSession } from "../session/SessionContext";
import { NotAvailable, Panel, formatCurrency, formatNumber, statusTone } from "./ui/Primitives";

type ScenarioType = "utilization_reduction" | "throughput_scaling" | "demand_uplift";

const SCENARIO_LABELS: Record<ScenarioType, string> = {
  utilization_reduction: "Utilization reduction",
  throughput_scaling: "Throughput change (user assumption)",
  demand_uplift: "Demand uplift",
};

export function WhatIfSimulator() {
  const { bottleneck, scenario, runScenario, busy, assumptions } = useSession();
  const [scenarioType, setScenarioType] = useState<ScenarioType>("utilization_reduction");
  const [change, setChange] = useState(10);
  const [acknowledged, setAcknowledged] = useState(false);

  const whatIf = bottleneck?.what_if_inputs;
  const utilizationAvailable = Boolean(whatIf?.current_utilization?.available);
  const baselineUnits = scenario?.baseline.units_per_day ?? null;

  useEffect(() => {
    if (!utilizationAvailable && whatIf?.station) setScenarioType("throughput_scaling");
  }, [utilizationAvailable, whatIf?.station]);

  const availability = useMemo(
    () => ({
      utilization_reduction: utilizationAvailable,
      throughput_scaling: Boolean(bottleneck),
      demand_uplift: baselineUnits !== null || Boolean(bottleneck),
    }),
    [utilizationAvailable, bottleneck, baselineUnits],
  );

  const run = () => {
    if (scenarioType === "utilization_reduction") {
      void runScenario("utilization_reduction", { utilization_reduction: change / 100 });
      return;
    }
    if (scenarioType === "throughput_scaling") {
      if (!acknowledged) return;
      void runScenario("throughput_scaling", { throughput_change: change / 100, scaling_basis: "user_assumption" });
      return;
    }
    void runScenario("demand_uplift", { demand_change: change / 100 });
  };

  const canRun = availability[scenarioType] && (scenarioType !== "throughput_scaling" || acknowledged) && !busy;

  return (
    <Panel
      title="What-if simulator"
      subtitle="Scenarios run on the backend against the observed baseline"
      actions={
        <button type="button" className="btn-primary" onClick={run} disabled={!canRun}>
          <FlaskConical size={11} aria-hidden />
          Run scenario
        </button>
      }
    >
      <div className="grid gap-4 px-4 py-4 lg:grid-cols-[320px_1fr]">
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="label">Scenario type</span>
            <select
              value={scenarioType}
              onChange={(event) => {
                setScenarioType(event.target.value as ScenarioType);
                setAcknowledged(false);
              }}
              className="border border-line bg-bg px-2 py-1.5 text-xs text-ink focus:border-cyan"
            >
              {(Object.keys(SCENARIO_LABELS) as ScenarioType[]).map((type) => (
                <option key={type} value={type} disabled={!availability[type]}>
                  {SCENARIO_LABELS[type]} {availability[type] ? "" : "(unavailable)"}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="label">
              {scenarioType === "utilization_reduction"
                ? "Utilization reduction"
                : scenarioType === "throughput_scaling"
                  ? "Throughput change"
                  : "Demand change"}{" "}
              · {change}%
            </span>
            <input
              type="range"
              min={scenarioType === "throughput_scaling" ? -20 : 0}
              max={scenarioType === "utilization_reduction" ? 50 : 30}
              value={change}
              onChange={(event) => setChange(Number(event.target.value))}
              className="accent-cyan"
              aria-label="Scenario change percentage"
            />
          </label>

          {scenarioType === "throughput_scaling" && (
            <label className="flex items-start gap-2 border border-warn/30 bg-warn/5 px-3 py-2">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(event) => setAcknowledged(event.target.checked)}
                className="mt-0.5 accent-cyan"
              />
              <span className="text-2xs leading-relaxed text-ink-2">
                I understand this scaling is a <span className="text-warn">user assumption</span>, not a data-derived
                relationship. The dataset's observed utilization/throughput comparison is demand-confounded.
              </span>
            </label>
          )}

          {!utilizationAvailable && scenarioType === "utilization_reduction" && (
            <NotAvailable reason="No utilization is available for the candidate station; utilization scenarios cannot run." />
          )}
        </div>

        <div className="min-w-0">
          {!scenario ? (
            <NotAvailable reason="No scenario has been run. Choose a type and run it — the backend computes the simulated result." />
          ) : (
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-px border border-line bg-line sm:grid-cols-3">
                <ScenarioStat
                  label="Baseline"
                  value={scenario.baseline.throughput_per_hour !== null ? formatNumber(scenario.baseline.throughput_per_hour, 2) : null}
                  unit="units/hour"
                  status="OBSERVED"
                />
                <ScenarioStat
                  label="Scenario"
                  value={
                    scenario.scenario.metrics.throughput_per_hour
                      ? formatNumber(scenario.scenario.metrics.throughput_per_hour.scenario, 2)
                      : scenario.scenario.units_per_day !== null
                        ? formatNumber(scenario.scenario.units_per_day, 0)
                        : null
                  }
                  unit={scenario.scenario.metrics.throughput_per_hour ? "units/hour" : "units/day"}
                  status="SIMULATED"
                />
                <ScenarioStat
                  label="Delta"
                  value={
                    scenario.economic_output.units_per_day_delta.value !== null
                      ? `${scenario.economic_output.units_per_day_delta.value >= 0 ? "+" : ""}${formatNumber(scenario.economic_output.units_per_day_delta.value, 0)}`
                      : null
                  }
                  unit="units/day"
                  status={scenario.economic_output.units_per_day_delta.status}
                />
                <ScenarioStat
                  label="Daily impact"
                  value={
                    scenario.economic_output.daily_contribution_delta.value !== null
                      ? formatCurrency(scenario.economic_output.daily_contribution_delta.value, scenario.baseline.economics.currency, 0)
                      : null
                  }
                  status={scenario.economic_output.daily_contribution_delta.status}
                />
                <ScenarioStat
                  label="Net daily"
                  value={
                    scenario.economic_output.net_daily_impact.value !== null
                      ? formatCurrency(scenario.economic_output.net_daily_impact.value, scenario.baseline.economics.currency, 0)
                      : null
                  }
                  status={scenario.economic_output.net_daily_impact.status}
                />
                <ScenarioStat
                  label="Method"
                  value={scenario.simulation_method ? scenario.simulation_method.slice(0, 28) : null}
                  status="SIMULATED"
                />
              </div>

              {scenario.warnings.length > 0 && (
                <ul className="flex flex-col gap-1 border border-warn/30 bg-warn/5 px-3 py-2.5">
                  {scenario.warnings.map((warning) => (
                    <li key={warning} className="text-2xs leading-relaxed text-ink-2">
                      {warning}
                    </li>
                  ))}
                </ul>
              )}

              <div className="flex flex-wrap items-center gap-2">
                <span className={`chip ${statusTone(scenario.epistemic_status)}`}>{scenario.epistemic_status}</span>
                {assumptions && (
                  <span className="text-2xs text-ink-3">
                    {Object.values(assumptions.assumptions).filter((entry) => entry.value !== null).length} assumption(s) applied
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      <p className="border-t border-line px-4 py-2 text-2xs text-ink-3">
        Simulated results are assumption-dependent and are not forecasts. No value is computed in the browser.
      </p>
    </Panel>
  );
}

function ScenarioStat({ label, value, unit, status }: { label: string; value: string | null; unit?: string; status: string }) {
  return (
    <div className="flex flex-col gap-1 bg-bg-2/80 px-3 py-2.5">
      <span className="label">{label}</span>
      {value === null ? (
        <span className="mono-value text-xs text-ink-3">NOT AVAILABLE</span>
      ) : (
        <span className="mono-value text-sm text-ink">
          {value}
          {unit && <span className="ml-1 text-2xs text-ink-3">{unit}</span>}
        </span>
      )}
      <span className={`chip w-fit ${statusTone(status)}`}>{status.replace(/_/g, " ")}</span>
    </div>
  );
}
