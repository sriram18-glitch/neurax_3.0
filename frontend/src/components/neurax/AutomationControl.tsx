import { Pause, Play, RotateCcw, SkipForward, Zap } from "lucide-react";

import { useSession } from "../../session/SessionContext";

/** Stream + auto-investigation controls. Every control hits the real backend
 * and operates on the currently selected inspection source. */
export function AutomationControl({ compact = false }: { compact?: boolean }) {
  const { stream, streamBusy, startStream, pauseStream, resetStream, setStreamSpeed, processNextFrame, autoInvestigation, setAutoInvestigation } =
    useSession();

  const running = Boolean(stream?.running);
  const exhausted = Boolean(stream && stream.remaining === 0 && stream.total_frames > 0);
  const hasSource = Boolean(stream?.source);
  const disabled = streamBusy || !hasSource;

  return (
    <div className={`flex flex-wrap items-center gap-2 ${compact ? "" : "px-1"}`}>
      <button
        type="button"
        className={`btn ${running ? "border-warn/50 bg-warn/10 text-warn" : "btn-primary"}`}
        onClick={() => (running ? void pauseStream() : void startStream())}
        disabled={disabled}
        aria-pressed={running}
      >
        {running ? <Pause size={12} aria-hidden /> : <Play size={12} aria-hidden />}
        {running ? "Pause" : exhausted ? "Restart stream" : "Start automated inspection"}
      </button>
      <button
        type="button"
        className="btn-ghost !px-2.5 !py-2"
        onClick={() => void processNextFrame()}
        disabled={disabled}
        title="Process the next real frame immediately"
      >
        <SkipForward size={12} aria-hidden />
        Next
      </button>
      <button
        type="button"
        className="btn-ghost !px-2.5 !py-2"
        onClick={() => void resetStream()}
        disabled={streamBusy}
        title="Reset the stream to frame 0"
      >
        <RotateCcw size={12} aria-hidden />
        Reset
      </button>

      <div className="flex items-center gap-1 border border-line/70 px-1.5 py-1" role="group" aria-label="Stream speed">
        {(stream?.speeds ?? [0.5, 1, 2, 5]).map((speed) => (
          <button
            key={speed}
            type="button"
            onClick={() => void setStreamSpeed(speed)}
            className={`px-2 py-0.5 font-mono text-2xs transition-colors ${
              stream?.speed === speed ? "bg-cyan/15 text-cyan" : "text-ink-3 hover:text-ink-2"
            }`}
            aria-pressed={stream?.speed === speed}
          >
            {speed}x
          </button>
        ))}
      </div>

      <button
        type="button"
        onClick={() => setAutoInvestigation(!autoInvestigation)}
        aria-pressed={autoInvestigation}
        className={`chip ${autoInvestigation ? "border-cyan/50 bg-cyan/10 text-cyan" : "border-line text-ink-3"}`}
        title="When a defect or review decision is produced, the investigation chain runs automatically."
      >
        <Zap size={10} aria-hidden />
        AUTO INVESTIGATION {autoInvestigation ? "ON" : "OFF"}
      </button>

      {!hasSource && (
        <span className="chip border-warn/40 text-warn">no inspection source — add data first</span>
      )}
    </div>
  );
}
