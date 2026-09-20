/** Shared clipboard helper: extract image files from a paste event. */
export function clipboardImageFiles(event: ClipboardEvent): File[] {
  const files: File[] = [];
  if (event.clipboardData?.files?.length) {
    files.push(...Array.from(event.clipboardData.files));
  }
  const items = event.clipboardData?.items;
  if (items) {
    for (const item of items) {
      if (item.kind === "file" && item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) files.push(file);
      }
    }
  }
  return files;
}