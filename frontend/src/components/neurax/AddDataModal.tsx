import { FlaskConical, FolderOpen, ImagePlus, Images } from "lucide-react";

/**
 * Add inspection data: three runtime input types (single image, image set,
 * folder dataset) plus the optional bundled demo source. All data is
 * user-selected from any accessible location - never a hardcoded path.
 */
export function AddDataModal({
  onClose,
  onImage,
  onImageSet,
  onFolder,
  onDemo,
}: {
  onClose: () => void;
  onImage: () => void;
  onImageSet: () => void;
  onFolder: () => void;
  onDemo: () => void;
}) {
  const options = [
    {
      icon: ImagePlus,
      title: "SINGLE IMAGE",
      text: "Select one image from anywhere on this computer. NEURAX validates and inspects it immediately.",
      action: onImage,
    },
    {
      icon: Images,
      title: "IMAGE SET",
      text: "Select multiple images from any folders. NEURAX validates the set, then auto-checks every image.",
      action: onImageSet,
    },
    {
      icon: FolderOpen,
      title: "DATASET / FOLDER",
      text: "Select an entire folder. Supported images are discovered (class subfolders become labels) and auto-inspected.",
      action: onFolder,
    },
  ];
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-6" role="dialog" aria-modal="true" aria-label="Add inspection data">
      <div className="hud w-full max-w-2xl p-6">
        <div className="mb-4 flex items-center justify-between">
          <p className="label">Add inspection data</p>
          <button type="button" className="btn-ghost !px-2 !py-1" onClick={onClose} aria-label="Close">
            Close
          </button>
        </div>
        <div className="grid gap-px bg-line/40 sm:grid-cols-3">
          {options.map(({ icon: Icon, title, text, action }) => (
            <button
              key={title}
              type="button"
              onClick={action}
              className="flex flex-col items-start gap-2.5 bg-panel/70 px-4 py-4 text-left transition-colors hover:bg-panel-2/70 hover:text-cyan"
            >
              <Icon size={16} className="text-cyan" aria-hidden />
              <span className="text-2xs font-semibold uppercase tracking-[0.12em] text-ink">{title}</span>
              <span className="text-[10px] leading-relaxed text-ink-3">{text}</span>
            </button>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line/60 pt-4">
          <button type="button" className="btn-ghost !px-3 !py-1.5" onClick={onDemo} title="Optional bundled sample dataset for demonstration only - never the default production source">
            <FlaskConical size={12} aria-hidden />
            Use built-in demo data
          </button>
          <p className="text-2xs leading-relaxed text-ink-3">
            Selected data is ingested into a local session source with generated IDs — no filesystem paths are stored or
            shown. The automated stream runs over the currently selected source.
          </p>
        </div>
      </div>
    </div>
  );
}