import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";

import type { VisionInspection } from "../../types/api";

type Mode = "original" | "localization" | "overlay";

/**
 * Localization viewer with an original / localization / overlay comparison.
 * The heatmap and region are model-derived; ground truth is reported absent.
 */
export function LocalizationCompare({
  imageUrl,
  inspection,
  heatmap,
  preprocessed,
}: {
  imageUrl: string;
  inspection: VisionInspection;
  heatmap?: string | null;
  preprocessed?: string | null;
}) {
  const [mode, setMode] = useState<Mode>("overlay");
  const [intensity, setIntensity] = useState(70);
  const reduceMotion = useReducedMotion();
  const box = inspection.localization.bounding_box;
  const width = inspection.image_metadata.width;
  const height = inspection.image_metadata.height;
  const heatSrc = heatmap ? `data:image/png;base64,${heatmap}` : null;

  return (
    <div className="flex flex-col gap-2 px-4 py-3">
      <div className="flex flex-wrap items-center gap-1">
        {(["original", "localization", "overlay"] as Mode[]).map((candidate) => (
          <button
            key={candidate}
            type="button"
            onClick={() => setMode(candidate)}
            aria-pressed={mode === candidate}
            className={`chip ${mode === candidate ? "border-cyan/50 bg-cyan/10 text-cyan" : "border-line text-ink-3 hover:text-ink-2"}`}
            disabled={candidate !== "original" && !heatSrc}
          >
            {candidate}
          </button>
        ))}
        <label className="ml-auto flex items-center gap-2 text-2xs text-ink-3">
          overlay
          <input
            type="range"
            min={10}
            max={100}
            value={intensity}
            onChange={(event) => setIntensity(Number(event.target.value))}
            className="w-24 accent-cyan"
            aria-label="Heatmap overlay intensity"
          />
          <span className="w-8 text-right font-mono text-[9px]">{intensity}%</span>
        </label>
      </div>

      <div className="relative mx-auto max-h-[46vh] overflow-hidden border border-line-2 bg-black">
        <img
          src={mode === "localization" && preprocessed ? `data:image/png;base64,${preprocessed}` : imageUrl}
          alt="Inspection with model-derived localization"
          className="max-h-[46vh] w-auto"
          draggable={false}
        />
        {heatSrc && mode !== "original" && (
          <motion.img
            src={heatSrc}
            alt="Model attention heatmap"
            className="pointer-events-none absolute inset-0 h-full w-full mix-blend-screen"
            initial={reduceMotion ? false : { opacity: 0 }}
            animate={{ opacity: (mode === "localization" ? 100 : intensity) / 100 }}
            transition={{ duration: 0.5 }}
          />
        )}
        {box && mode !== "original" && (
          <motion.div
            className="pointer-events-none absolute border-2 border-cyan"
            style={{
              left: `${(box.x / width) * 100}%`,
              top: `${(box.y / height) * 100}%`,
              width: `${(box.width / width) * 100}%`,
              height: `${(box.height / height) * 100}%`,
            }}
            initial={reduceMotion ? false : { opacity: 0, scale: 1.2 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.4 }}
          >
            <span className="absolute -top-5 left-0 whitespace-nowrap bg-cyan/20 px-1 font-mono text-2xs text-cyan">
              MODEL-DERIVED REGION
            </span>
          </motion.div>
        )}
      </div>

      <p className="text-2xs leading-relaxed text-ink-3">
        {inspection.localization.method} · <span className="text-novel">MODEL-DERIVED LOCALIZATION</span> · ground truth:{" "}
        <span className="font-mono text-warn">NOT AVAILABLE</span> (the image dataset has no defect annotations)
      </p>
    </div>
  );
}
