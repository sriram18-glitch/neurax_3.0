import { useState } from "react";
import { Save } from "lucide-react";

import { useSession } from "../session/SessionContext";
import { NotAvailable, Panel, formatCurrency, formatNumber, statusIcon, statusTone } from "./ui/Primitives";

const PRIMARY_FIELDS = [
  { key: "contribution_margin_per_unit", label: "Contribution margin", unit: "currency/unit", step: "0.01" },
  { key: "working_hours_per_day", label: "Working hours", unit: "hours/day", step: "0.5" },
  { key: "working_days_per_month", label: "Working days", unit: "days/month", step: "1" },
  { key: "intervention_cost", label: "Intervention cost", unit: "currency (one-time)", step: "100" },
] as const;

export function EconomicPanel() {
  const { assumptions, baseline, saveAssumptions, busy, bottleneck } = useSession();
  const [currency, setCurrency] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});

  const supplied = assumptions?.assumptions ?? {};
  const missing = Object.entries(supplied)
    .filter(([, entry]) => entry.value === null)
    .map(([field]) => field);

  const handleSave = () => {
    const updates: Record<string, string | number | null> = {};
    if (currency.trim()) updates.currency = currency.trim();
    for (const field of PRIMARY_FIELDS) {
      const raw = values[field.key];
      if (raw !== undefined && raw !== "") updates[field.key] = Number(raw);
    }
    if (Object.keys(updates).length) void saveAssumptions(updates);
  };

  const dailyContribution = baseline?.baseline.daily_contribution;
  const unitsPerDay = baseline?.baseline.units_per_day;

  return (
    <Panel
      title="Economic baseline"
      subtitle={baseline ? `throughput source: ${baseline.throughput_source ?? "unknown"}` : "Requires assumptions"}
      actions={
        <button type="button" className="btn-ghost" onClick={handleSave} disabled={Boolean(busy)}>
          <Save size={11} aria-hidden />
          Save assumptions
        </button>
      }
    >
      <div className="grid gap-4 px-4 py-4 lg:grid-cols-2">
        <div className="flex flex-col gap-3">
          <p className="label">User assumptions — no defaults exist</p>
          <label className="flex items-center justify-between gap-3 border border-line px-3 py-2">
            <span className="text-xs text-ink-2">Currency</span>
            <input
              type="text"
              value={currency}
              placeholder={assumptions?.currency.value ?? "NOT_PROVIDED"}
              onChange={(event) => setCurrency(event.target.value.toUpperCase())}
              maxLength={8}
              className="w-24 border border-line bg-bg px-2 py-1 text-right font-mono text-xs text-ink focus:border-cyan"
            />
          </label>
          {PRIMARY_FIELDS.map((field) => {
            const entry = supplied[field.key];
            return (
              <label key={field.key} className="flex items-center justify-between gap-3 border border-line px-3 py-2">
                <span className="min-w-0">
                  <span className="block text-xs text-ink-2">{field.label}</span>
                  <span className="block text-2xs text-ink-3">{field.unit}</span>
                </span>
                <span className="flex items-center gap-2">
                  {entry?.source === "USER_ASSUMPTION" && <span className="chip border-ok/40 text-ok">SET</span>}
                  <input
                    type="number"
                    step={field.step}
                    min={0}
                    value={values[field.key] ?? ""}
                    placeholder={entry?.value !== null && entry?.value !== undefined ? String(entry.value) : "NOT_PROVIDED"}
                    onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.value }))}
                    className="w-28 border border-line bg-bg px-2 py-1 text-right font-mono text-xs text-ink focus:border-cyan"
                  />
                </span>
              </label>
            );
          })}
          <p className="text-2xs leading-relaxed text-ink-3">
            {!assumptions
              ? "Assumption status not loaded yet. Saving supplies values — the system never invents economic defaults."
              : missing.length > 0
                ? `${missing.length} field(s) still NOT_PROVIDED. Economic outputs remain NOT AVAILABLE until supplied.`
                : "All fields supplied. Baseline and scenarios can be calculated."}
          </p>
        </div>

        <div className="flex flex-col gap-3">
          <p className="label">Calculated baseline</p>
          {!baseline ? (
            <NotAvailable reason="No baseline has been computed. Supply assumptions to calculate." />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-px border border-line bg-line">
                <Stat
                  label="Observed throughput"
                  value={baseline.baseline.throughput_per_hour.value !== null ? formatNumber(baseline.baseline.throughput_per_hour.value, 2) : null}
                  unit="units/hour"
                  status="DATA_DERIVED"
                />
                <Stat
                  label="Units per day"
                  value={unitsPerDay?.value !== null && unitsPerDay?.value !== undefined ? formatNumber(unitsPerDay.value, 0) : null}
                  unit="units/day"
                  status={unitsPerDay?.status ?? "NOT_AVAILABLE"}
                />
                <Stat
                  label="Daily contribution"
                  value={dailyContribution?.value !== null && dailyContribution?.value !== undefined ? formatCurrency(dailyContribution.value, baseline.currency, 0) : null}
                  status={dailyContribution?.status ?? "NOT_AVAILABLE"}
                />
                <Stat
                  label="Monthly contribution"
                  value={
                    baseline.baseline.monthly_contribution.value !== null && baseline.baseline.monthly_contribution.value !== undefined
                      ? formatCurrency(baseline.baseline.monthly_contribution.value, baseline.currency, 0)
                      : null
                  }
                  status={baseline.baseline.monthly_contribution.status}
                />
              </div>
              <div className="border border-line px-3 py-2.5">
                <p className="label mb-1">Formula</p>
                <p className="font-mono text-2xs text-ink-2">{dailyContribution?.formula}</p>
                {dailyContribution?.missing_inputs && dailyContribution.missing_inputs.length > 0 && (
                  <p className="mt-1.5 text-2xs text-warn">Missing: {dailyContribution.missing_inputs.join(", ")}</p>
                )}
              </div>
              {bottleneck?.candidate_bottleneck.station && (
                <p className="text-2xs text-ink-3">
                  Baseline relates to the candidate constraint <span className="text-ink-2">{bottleneck.candidate_bottleneck.station}</span>.
                </p>
              )}
            </>
          )}
        </div>
      </div>
      <p className="border-t border-line px-4 py-2 text-2xs text-ink-3">
        Calculations use observed throughput and user-supplied assumptions only. No economic value is invented by the system.
      </p>
    </Panel>
  );
}

function Stat({ label, value, unit, status }: { label: string; value: string | null; unit?: string; status: string }) {
  return (
    <div className="flex flex-col gap-1 bg-bg-2/80 px-3 py-3">
      <span className="label">{label}</span>
      {value === null ? (
        <span className="mono-value text-sm text-ink-3">NOT AVAILABLE</span>
      ) : (
        <span className="mono-value text-base text-ink">
          {value}
          {unit && <span className="ml-1 text-2xs text-ink-3">{unit}</span>}
        </span>
      )}
      <span className={`chip w-fit ${statusTone(status)}`}>
        {statusIcon(status)}
        {status.replace(/_/g, " ")}
      </span>
    </div>
  );
}
