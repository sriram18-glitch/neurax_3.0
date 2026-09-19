import { useMemo, useState } from "react";
import { ChevronDown, RefreshCw, RotateCcw, ScanSearch, Upload } from "lucide-react";

import { useSession } from "../session/SessionContext";

export function CommandBar({ onUploadClick }: { onUploadClick: () => void }) {
  const { contract, datasets, datasetId, loadDataset, busy, refreshDatasets, refreshVision, backendOnline, visionStatus, reset } =
    useSession();
  const [open, setOpen] = useState(false);

  const datasetLabel = useMemo(() => contract?.filename ?? "No process dataset", [contract]);

  return (
    <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-line bg-bg-2/70 px-4 py-2.5 backdrop-blur">
      <div className="flex items-center gap-3">
        <div className="flex h-6 w-6 items-center justify-center border border-cyan/50 bg-cyan/10">
          <span className="font-mono text-[10px] font-bold text-cyan">NX</span>
        </div>
        <div>
          <p className="text-xs font-semibold tracking-[0.16em] text-ink">NEURAX</p>
          <p className="text-2xs text-ink-3">Industrial inspection workstation</p>
        </div>
      </div>

      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="flex items-center gap-2 border border-line px-3 py-1.5 text-left transition-colors hover:border-line-2"
          aria-expanded={open}
          aria-haspopup="listbox"
        >
          <div className="min-w-0">
            <p className="text-2xs uppercase tracking-[0.12em] text-ink-3">Process dataset</p>
            <p className="max-w-[220px] truncate text-xs text-ink">{datasetLabel}</p>
          </div>
          <ChevronDown size={13} className="text-ink-3" aria-hidden />
        </button>
        {open && (
          <div role="listbox" className="absolute left-0 top-full z-30 mt-1 w-[340px] border border-line-2 bg-bg-2 shadow-lift">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onUploadClick();
              }}
              className="flex w-full items-center gap-2 border-b border-line px-3 py-2 text-xs text-cyan hover:bg-panel-2"
            >
              <Upload size={12} aria-hidden />
              Upload new process dataset
            </button>
            <div className="max-h-64 overflow-y-auto">
              {datasets.length === 0 && <p className="px-3 py-3 text-2xs text-ink-3">No processed datasets</p>}
              {datasets.map((dataset) => (
                <button
                  key={dataset.dataset_id}
                  type="button"
                  role="option"
                  aria-selected={dataset.dataset_id === datasetId}
                  onClick={() => {
                    setOpen(false);
                    void loadDataset(dataset.dataset_id);
                  }}
                  className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-xs transition-colors hover:bg-panel-2 ${
                    dataset.dataset_id === datasetId ? "bg-cyan/5 text-cyan" : "text-ink-2"
                  }`}
                >
                  <span className="truncate">{dataset.filename ?? dataset.dataset_id}</span>
                  <span className="shrink-0 font-mono text-2xs text-ink-3">
                    {dataset.rows !== null ? `${dataset.rows.toLocaleString()} rows` : dataset.status}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <dl className="flex flex-wrap items-center gap-x-6 gap-y-1">
        <StatusItem
          label="Backend"
          value={backendOnline === null ? "CHECKING" : backendOnline ? "ONLINE" : "OFFLINE"}
          tone={backendOnline === null ? "idle" : backendOnline ? "ok" : "bad"}
        />
        <StatusItem
          label="Vision model"
          value={visionStatus?.model_available ? `READY · ${visionStatus.classes?.length ?? 0} classes` : "NOT TRAINED"}
          tone={visionStatus?.model_available ? "ok" : "idle"}
        />
      </dl>

      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          className="btn-ghost"
          onClick={() => {
            void refreshDatasets();
            void refreshVision();
          }}
          disabled={Boolean(busy)}
        >
          <RefreshCw size={12} className={busy ? "animate-spin" : ""} aria-hidden />
          Refresh
        </button>
        <button
          type="button"
          className="btn-ghost"
          onClick={() => reset()}
          disabled={Boolean(busy) || !contract}
          title="Clear the active process session. Processed datasets and artifacts are preserved."
        >
          <RotateCcw size={12} aria-hidden />
          Reset
        </button>
        <button type="button" className="btn-primary" onClick={onUploadClick} disabled={Boolean(busy)}>
          <ScanSearch size={12} aria-hidden />
          Process data
        </button>
      </div>
    </header>
  );
}

function StatusItem({ label, value, tone = "idle" }: { label: string; value: string; tone?: "ok" | "bad" | "idle" }) {
  const color = tone === "ok" ? "text-ok" : tone === "bad" ? "text-bad" : "text-ink-2";
  return (
    <div className="min-w-0">
      <dt className="text-2xs uppercase tracking-[0.12em] text-ink-3">{label}</dt>
      <dd className={`truncate font-mono text-2xs ${color}`}>{value}</dd>
    </div>
  );
}
