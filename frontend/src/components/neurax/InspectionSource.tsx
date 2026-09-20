import { FolderOpen, RefreshCcw, ScanSearch } from "lucide-react";

import { useSession } from "../../session/SessionContext";

/**
 * Current inspection source status. Sources are user-selected at runtime
 * (single image / image set / folder / built-in demo) - never a hardcoded
 * dataset path. Absolute filesystem paths are never shown.
 */
export function InspectionSourceBar({
  onAddData,
  compact = false,
}: {
  onAddData: () => void;
  compact?: boolean;
}) {
  const { currentSource, sources, changeSource, deleteSource, sourceBusy } = useSession();

  if (!currentSource) {
    return (
      <div className={`flex flex-wrap items-center justify-between gap-2 ${compact ? "px-1 py-1" : "px-4 py-3"}`}>
        <div>
          <p className="label">Inspection source</p>
          <p className="mt-0.5 text-2xs font-semibold uppercase tracking-[0.12em] text-warn">No inspection source</p>
          <p className="mt-0.5 text-2xs text-ink-3">Add an image, image set, or dataset to begin AI inspection.</p>
        </div>
        <button type="button" className="btn-primary !px-3 !py-1.5" onClick={onAddData}>
          <FolderOpen size={12} aria-hidden />
          Add inspection data
        </button>
      </div>
    );
  }

  const summary = currentSource.summary;
  const isDemo = currentSource.source_type === "BUILT_IN_DEMO";
  const displayName = isDemo ? "Bundled demo dataset" : currentSource.display_name;

  return (
    <div className={`flex flex-wrap items-center justify-between gap-2 ${compact ? "px-1 py-1" : "px-4 py-3"}`}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <div>
          <p className="label">Inspection source</p>
          <p className="flex items-center gap-2 font-mono text-xs text-ink">
            <span className={`h-1.5 w-1.5 rounded-full ${isDemo ? "bg-warn" : "bg-ok"}`} aria-hidden />
            {currentSource.type_label}
          </p>
        </div>
        <div>
          <p className="label">name</p>
          <p className="max-w-[220px] truncate font-mono text-xs text-ink-2">{displayName}</p>
        </div>
        <div>
          <p className="label">images</p>
          <p className="font-mono text-xs text-ink-2">
            {summary.valid} <span className="text-ink-3">valid</span>
            {summary.invalid > 0 && <span className="text-bad"> · {summary.invalid} invalid</span>}
            {summary.unsupported > 0 && <span className="text-warn"> · {summary.unsupported} unsupported</span>}
            {summary.duplicates > 0 && <span className="text-warn"> · {summary.duplicates} duplicates</span>}
          </p>
        </div>
        {isDemo && (
          <span className="chip border-warn/40 text-warn">BUILT-IN DEMO — not a production source</span>
        )}
      </div>
      <div className="flex items-center gap-2">
        {sources.length > 1 && (
          <div className="flex items-center gap-1">
            {sources.slice(0, 5).map((source) => (
              <button
                key={source.source_id}
                type="button"
                onClick={() => void changeSource(source.source_id)}
                disabled={sourceBusy || source.source_id === currentSource.source_id}
                className={`chip ${source.source_id === currentSource.source_id ? "border-cyan/50 bg-cyan/10 text-cyan" : "border-line text-ink-3 hover:text-ink-2"}`}
                title={`Switch to ${source.display_name}`}
              >
                {source.display_name}
              </button>
            ))}
          </div>
        )}
        <button type="button" className="btn-ghost !px-2.5 !py-1.5" onClick={onAddData}>
          <RefreshCcw size={11} aria-hidden />
          Change source
        </button>
        {!isDemo && (
          <button
            type="button"
            className="btn-ghost !px-2 !py-1"
            onClick={() => void deleteSource(currentSource.source_id)}
            disabled={sourceBusy}
            title="Remove this source and its ingested files"
          >
            <ScanSearch size={11} aria-hidden />
            Remove
          </button>
        )}
      </div>
    </div>
  );
}