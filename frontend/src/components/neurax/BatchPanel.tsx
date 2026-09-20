import { useCallback, useRef, useState } from "react";
import { FileUp, FolderOpen, Play, ScanLine, UploadCloud, X } from "lucide-react";

import { useSession } from "../../session/SessionContext";
import { useBatchPoll } from "../../session/useBatchPoll";
import type { BatchRecord } from "../../types/api";
import { DataGap } from "./DataGap";
import { EvidenceBadge } from "./EvidenceBadge";
import { AnimatedNumber, HudPanel } from "./Motion";
import { BatchGallery } from "./BatchGallery";

/**
 * Source ingestion: ADD DATA → validate → data health → auto check
 * (real pipeline) → per-image results → review queue.
 * The source is user-selected at runtime (image set or folder) and ingested
 * into a local session source - never a hardcoded dataset path.
 */
export function BatchPanel({ mode = "image-set" }: { mode?: "image-set" | "folder" }) {
  const { batch, batchBusy, batchError, createSource, inspectBatch, refreshBatch } = useSession();
  const [dragging, setDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  useBatchPoll(batch?.status === "inspecting" ? batch.batch_id : null);

  const handleFiles = useCallback(
    (files: FileList | null) => {
      const list = files ? Array.from(files) : [];
      if (list.length === 0) return;
      const display = list.length === 1 ? list[0].name : `${list.length} files`;
      setFileName(display);
      const sourceType = mode === "folder" ? "FOLDER_DATASET" : list.length === 1 ? "SINGLE_IMAGE" : "IMAGE_SET";
      void createSource(list, sourceType, mode === "folder" ? "Selected folder" : undefined);
    },
    [createSource, mode],
  );

  if (!batch) {
    return (
      <HudPanel title="Add inspection data" subtitle={mode === "folder" ? "folder dataset — NEURAX discovers and validates every supported image" : "image set — NEURAX validates, then inspects every image"}>
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            handleFiles(event.dataTransfer.files);
          }}
          className={`flex flex-col items-center gap-4 px-6 py-14 text-center ${dragging ? "ring-1 ring-cyan/50" : ""}`}
        >
          <div className="flex h-12 w-12 items-center justify-center border border-dashed border-line-2">
            <FolderOpen size={20} className="text-ink-3" aria-hidden />
          </div>
          <div>
            <p className="text-sm text-ink-2">{mode === "folder" ? "Select a folder — images are discovered automatically" : "Drop images here"}</p>
            <p className="mt-1 text-2xs leading-relaxed text-ink-3">
              {mode === "folder"
                ? "Supported: PNG · JPG · JPEG · WEBP · BMP · TIFF. Class subfolders become labels for measured decision quality."
                : "Select multiple images from any folder on this computer. Supported: PNG · JPG · JPEG · WEBP · BMP · TIFF."}
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-2">
            <button type="button" className="btn-primary" onClick={() => inputRef.current?.click()} disabled={batchBusy}>
              <UploadCloud size={12} aria-hidden />
              {mode === "folder" ? "Browse folder" : "Browse files"}
            </button>
            <span className="text-2xs text-ink-3">or drag and drop</span>
          </div>
          <input
            ref={inputRef}
            type="file"
            multiple
            {...(mode === "folder" ? ({ webkitdirectory: "", directory: "" } as Record<string, string>) : {})}
            accept=".png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff"
            className="sr-only"
            onChange={(event) => {
              handleFiles(event.target.files);
              event.target.value = "";
            }}
            aria-label={mode === "folder" ? "Select inspection folder" : "Add inspection images"}
          />
          {fileName && (
            <p className="flex items-center gap-2 font-mono text-2xs text-cyan">
              <ScanLine size={10} aria-hidden />
              {fileName} — validating…
            </p>
          )}
        </div>
        <p className="border-t border-line/60 px-4 py-2 text-2xs leading-relaxed text-ink-3">
          Every image receives its own inspection result with confidence, novelty, localization and decision. Nothing is
          silently discarded — invalid and unsupported files are counted in the data-health report.
        </p>
      </HudPanel>
    );
  }

  if (batch.status === "validated") {
    return (
      <div className="flex flex-col gap-3">
        <HudPanel
          title="Data health"
          subtitle={batch.batch_id}
          actions={
            <button
              type="button"
              className="btn-ghost !px-2 !py-1"
              onClick={() => {
                setFileName(null);
                void refreshBatch(batch.batch_id);
              }}
            >
              <X size={11} aria-hidden />
              Re-validate
            </button>
          }
        >
          <ValidationReport batch={batch} />
          {batchError && (
            <p className="border-t border-bad/40 bg-bad/10 px-4 py-2 text-2xs text-bad">{batchError.message}</p>
          )}
        </HudPanel>
        <HudPanel title="Ready to inspect" subtitle="runs the real inspection pipeline over every valid image">
          <div className="flex flex-col gap-2 px-4 py-4">
            <p className="text-2xs leading-relaxed text-ink-3">
              {batch.summary.valid} valid image(s) will be processed automatically. Each one gets a confidence, novelty
              check, localization and PASS/DEFECT/REVIEW decision.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="btn-primary"
                onClick={() => {
                  setFileName(null);
                  void inspectBatch(batch.batch_id);
                }}
                disabled={batchBusy || batch.summary.valid === 0}
              >
                <Play size={12} aria-hidden />
                Start auto check
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => {
                  setFileName(null);
                  void refreshBatch(batch.batch_id);
                }}
              >
                <FileUp size={11} aria-hidden />
                Add more images
              </button>
            </div>
          </div>
        </HudPanel>
      </div>
    );
  }

  if (batch.status === "inspecting" || batch.status === "failed") {
    const progress = batch.progress.total > 0 ? (batch.progress.inspected / batch.progress.total) * 100 : 0;
    return (
      <HudPanel title="Inspecting dataset" subtitle={batch.batch_id}>
        <div className="flex flex-col gap-3 px-4 py-4">
          {batch.status === "failed" ? (
            <DataGap title="Batch inspection failed" reason="The inspection engine could not complete the batch. Check the backend log and re-upload." />
          ) : (
            <>
              <div className="flex flex-wrap items-end gap-x-8 gap-y-2">
                <p className="font-mono text-3xl text-ink">
                  <AnimatedNumber value={batch.progress.inspected} />
                  <span className="text-ink-3"> / {batch.progress.total}</span>
                </p>
                <p className="text-2xs uppercase tracking-[0.12em] text-ink-3">real progress from the backend</p>
              </div>
              <div className="h-2 w-full bg-line/50">
                <div className="h-full bg-cyan/80 transition-[width] duration-700" style={{ width: `${progress}%` }} />
              </div>
              <div className="grid grid-cols-3 gap-px bg-line/40">
                <DecisionCount label="PASS" value={batch.decisions.PASS} tone="text-ok" />
                <DecisionCount label="DEFECT" value={batch.decisions.DEFECT} tone="text-bad" />
                <DecisionCount label="REVIEW" value={batch.decisions.REVIEW} tone="text-warn" />
              </div>
            </>
          )}
        </div>
      </HudPanel>
    );
  }

  return <BatchGallery batch={batch} />;
}

function DecisionCount({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="flex flex-col items-center gap-0.5 bg-panel/70 py-2">
      <AnimatedNumber value={value} className={`font-mono text-lg ${tone}`} />
      <span className="text-[9px] uppercase tracking-[0.12em] text-ink-3">{label}</span>
    </div>
  );
}

/** The data-health report: every number is the actual validation result. */
export function ValidationReport({ batch }: { batch: BatchRecord }) {
  const { summary } = batch;
  const validPercent = summary.total > 0 ? (summary.valid / summary.total) * 100 : 0;
  return (
    <div className="flex flex-col gap-3 px-4 py-3">
      <div className="grid grid-cols-2 gap-px bg-line/40 sm:grid-cols-4">
        <HealthStat label="images" value={summary.total} />
        <HealthStat label="valid" value={summary.valid} tone="text-ok" />
        <HealthStat label="invalid" value={summary.invalid} tone="text-bad" />
        <HealthStat label="unsupported" value={summary.unsupported} tone="text-warn" />
      </div>
      {summary.duplicates > 0 && (
        <p className="text-2xs text-warn">{summary.duplicates} duplicate image(s) detected by content hash and excluded from inspection.</p>
      )}
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="label">dataset validation</span>
          <span className="font-mono text-2xs text-ink-3">{validPercent.toFixed(0)}% valid</span>
        </div>
        <div className="h-2 w-full bg-line/50">
          <div className="h-full bg-ok/80" style={{ width: `${validPercent}%` }} />
        </div>
      </div>

      <div className="grid gap-px bg-line/40 sm:grid-cols-2">
        <AvailabilityRow label="Labels" value={summary.labels_available ? "AVAILABLE" : "NOT AVAILABLE"} detail={summary.labels_note} />
        <AvailabilityRow label="Class balance" value={summary.class_balance} detail={`${Object.entries(summary.class_counts).map(([name, count]) => `${name}: ${count}`).join(" · ") || "no classes"}`} />
        <AvailabilityRow label="Localization annotations" value={summary.localization_annotations} detail={summary.localization_note} />
        <AvailabilityRow label="Process join" value={summary.process_join} detail={summary.process_join_note} />
      </div>

      <p className="flex items-center gap-2 text-2xs text-ink-3">
        <EvidenceBadge status="OBSERVED" />
        validation results are measured per file — nothing is silently discarded
      </p>
    </div>
  );
}

function HealthStat({ label, value, tone = "text-ink" }: { label: string; value: number; tone?: string }) {
  return (
    <div className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2.5">
      <span className="label">{label}</span>
      <AnimatedNumber value={value} className={`font-mono text-lg ${tone}`} />
    </div>
  );
}

function AvailabilityRow({ label, value, detail }: { label: string; value: string; detail: string }) {
  const available = value === "AVAILABLE" || value === "BALANCED";
  return (
    <div className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2.5">
      <span className="flex items-center justify-between gap-2">
        <span className="label">{label}</span>
        <span className={`font-mono text-[9px] tracking-[0.08em] ${available ? "text-ok" : "text-ink-3"}`}>{value}</span>
      </span>
      <span className="text-[9px] leading-relaxed text-ink-3">{detail}</span>
    </div>
  );
}