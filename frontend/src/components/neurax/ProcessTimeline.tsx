import { useSession } from "../../session/SessionContext";
import { DataGap } from "./DataGap";

const SERIES_TONES = ["#38d6e0", "#a78bfa", "#f0b429", "#43d17a"];

/** Process timeline: binned real series with drift and event markers. */
export function ProcessTimeline() {
  const { timeline, timelineBusy, refreshTimeline, contract } = useSession();

  if (!contract) {
    return (
      <DataGap
        title="Process data not loaded"
        reason="Load or connect a process dataset to build the process timeline. The stream can run without it, but process evidence needs data."
      />
    );
  }

  if (timelineBusy) {
    return <p className="px-4 py-3 text-2xs text-ink-3">Building the timeline from the processed-data artifact…</p>;
  }

  if (!timeline || timeline.status !== "AVAILABLE" || timeline.series.length === 0) {
    return (
      <DataGap
        title="Timeline not built yet"
        reason={timeline?.reason ?? "The timeline aggregates real processed-data series; build it for this dataset."}
        action={
          <button type="button" className="btn-ghost !px-2.5 !py-1" onClick={() => void refreshTimeline()}>
            Build timeline
          </button>
        }
      />
    );
  }

  const bins = timeline.bins ?? 48;
  const width = 900;
  const laneHeight = 44;
  const laneGap = 14;
  const height = timeline.series.length * (laneHeight + laneGap) + 34;
  const toX = (index: number) => (index / Math.max(1, bins - 1)) * (width - 70) + 50;
  const driftBins = new Set(timeline.drift_markers.map((marker) => marker.bin));

  return (
    <div className="flex flex-col gap-2 px-4 py-3">
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full min-w-[640px]" role="img" aria-label="Process timeline with drift and event markers">
          {timeline.series.map((series, lane) => {
            const top = 24 + lane * (laneHeight + laneGap);
            const max = Math.max(...series.values, 0.0001);
            const min = Math.min(...series.values, 0);
            const range = max - min || 1;
            const path = series.values
              .map((value, index) => `${index === 0 ? "M" : "L"} ${toX(index).toFixed(1)} ${(top + laneHeight - ((value - min) / range) * laneHeight).toFixed(1)}`)
              .join(" ");
            const tone = SERIES_TONES[lane % SERIES_TONES.length];
            return (
              <g key={`${series.station}-${series.metric}`}>
                <text x={0} y={top + 10} fill="#8ea0b5" fontSize={9} fontFamily="var(--font-mono)">
                  {series.station}
                </text>
                <text x={0} y={top + 22} fill="#5f7085" fontSize={8} fontFamily="var(--font-mono)">
                  {series.metric}
                </text>
                <line x1={50} y1={top + laneHeight} x2={width - 20} y2={top + laneHeight} stroke="rgb(var(--line) / 0.45)" />
                <path d={path} fill="none" stroke={tone} strokeWidth={1.6} opacity={0.9} />
                <text x={width - 16} y={top + 10} fill={tone} fontSize={9} fontFamily="var(--font-mono)" textAnchor="end">
                  {max.toFixed(series.unit === "ratio" ? 2 : 0)}
                </text>
              </g>
            );
          })}

          {[...driftBins].map((bin) => (
            <line
              key={`drift-${bin}`}
              x1={toX(bin)}
              y1={14}
              x2={toX(bin)}
              y2={height - 22}
              stroke="#a78bfa"
              strokeWidth={1}
              strokeDasharray="3 3"
              opacity={0.75}
            />
          ))}

          {timeline.event_markers.slice(0, 40).map((marker, index) => (
            <circle key={`event-${index}`} cx={toX(marker.bin)} cy={14} r={3} fill="#ef5f6b" opacity={0.9} />
          ))}

          <text x={50} y={height - 6} fill="#5f7085" fontSize={8} fontFamily="var(--font-mono)">
            {timeline.order_basis}
          </text>
        </svg>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-2xs text-ink-3">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-4 bg-cyan" aria-hidden /> station series (real means per bin)
        </span>
        {timeline.drift_markers.length > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="h-3 w-px border-l border-dashed border-novel" aria-hidden /> drift change point ·{" "}
            {timeline.drift_markers.map((marker) => marker.column).join(", ")}
          </span>
        )}
        {timeline.event_markers.length > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-bad" aria-hidden /> event rows ({timeline.event_definition?.target}{" "}
            {timeline.event_definition?.direction} tail, threshold {timeline.event_definition?.threshold})
          </span>
        )}
      </div>
      <p className="text-2xs leading-relaxed text-ink-3">{timeline.note}</p>
    </div>
  );
}
