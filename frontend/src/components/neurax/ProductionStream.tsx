import { Camera, Film } from "lucide-react";

import { useSession } from "../../session/SessionContext";

const DECISION_TONE: Record<string, string> = {
  PASS: "text-ok",
  DEFECT: "text-bad",
  REVIEW: "text-warn",
};

/** The simulated production stream: real dataset frames in a deterministic order. */
export function ProductionStream({ onSelectInspection }: { onSelectInspection?: (inspectionId: string) => void }) {
  const { stream, loadInspection } = useSession();
  if (!stream) {
    return <p className="px-4 py-3 text-2xs text-ink-3">Connecting to the production stream…</p>;
  }

  const progress = stream.total_frames > 0 ? (stream.frame_number / stream.total_frames) * 100 : 0;
  const counts = stream.decision_counts ?? {};

  return (
    <div className="flex flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line/60 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Camera size={12} className={stream.running ? "text-cyan" : "text-ink-3"} aria-hidden />
          <div>
            <p className="font-mono text-2xs uppercase tracking-[0.1em] text-ink-2">{stream.station_id}</p>
            <p className="text-[9px] uppercase tracking-[0.12em] text-warn">{stream.label}</p>
          </div>
        </div>
        <div className="text-right">
          <p className="font-mono text-sm text-ink">
            {stream.frame_number.toLocaleString("en-US")}
            <span className="text-ink-3"> / {stream.total_frames.toLocaleString("en-US")}</span>
          </p>
          <p className="text-[9px] uppercase tracking-[0.1em] text-ink-3">
            {stream.running ? "streaming" : stream.processed > 0 ? "paused" : "ready"} · {stream.processed} processed
          </p>
        </div>
      </div>

      <div className="px-4 pt-2.5">
        <div className="h-1 w-full bg-line/50">
          <div className="h-full bg-cyan/70 transition-[width] duration-500" style={{ width: `${progress}%` }} />
        </div>
        <p className="mt-1.5 text-[9px] text-ink-3">{stream.note}</p>
      </div>

      <div className="grid grid-cols-3 gap-px bg-line/40 p-px">
        {(["PASS", "DEFECT", "REVIEW"] as const).map((decision) => (
          <div key={decision} className="flex flex-col items-center gap-0.5 bg-panel/70 py-2">
            <span className={`font-mono text-lg ${DECISION_TONE[decision]}`}>{counts[decision] ?? 0}</span>
            <span className="text-[9px] uppercase tracking-[0.12em] text-ink-3">{decision}</span>
          </div>
        ))}
      </div>

      {stream.next_frame && (
        <p className="flex items-center gap-1.5 border-t border-line/60 px-4 py-2 text-2xs text-ink-3">
          <Film size={10} aria-hidden />
          next frame: <span className="font-mono text-ink-2">{stream.next_frame.filename}</span>
          <span className="text-ink-3">({stream.next_frame.class_folder})</span>
        </p>
      )}

      <div className="max-h-56 overflow-y-auto border-t border-line/60">
        {stream.history.length === 0 ? (
          <p className="px-4 py-3 text-2xs text-ink-3">No frames processed yet. Start the stream to run real inspections.</p>
        ) : (
          <ul>
            {stream.history.map((entry) => (
              <li key={entry.inspection_id}>
                <button
                  type="button"
                  onClick={() => {
                    if (onSelectInspection) onSelectInspection(entry.inspection_id);
                    else void loadInspection(entry.inspection_id);
                  }}
                  className="flex w-full items-center justify-between gap-2 border-b border-line/30 px-4 py-1.5 text-left transition-colors hover:bg-panel-2/40"
                >
                  <span className="truncate font-mono text-2xs text-ink-3">{entry.filename}</span>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="font-mono text-[9px] text-ink-3">{(entry.confidence * 100).toFixed(0)}%</span>
                    <span className={`font-mono text-2xs ${DECISION_TONE[entry.decision] ?? "text-ink-2"}`}>{entry.decision}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
