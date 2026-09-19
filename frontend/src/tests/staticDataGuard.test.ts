/**
 * Static-data guard (Phase 10 §39).
 *
 * Judge-visible results must never be hardcoded in UI source. This test scans
 * every component/view file for:
 *   - real dataset station names appearing as literals
 *   - real computed values from our actual runs (throughput, economics, scores)
 *   - currency symbols attached to numbers
 *
 * Labels and explanatory copy are allowed; result values are not.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");

// Station names that exist only in the organizer datasets. If any appears in a
// component file, someone hardcoded a result.
const FORBIDDEN_STATION_LITERALS = [
  "Assembly",
  "Drilling",
  "Milling",
  "Blanking",
  "Forklift",
  "Warehouse1",
  "Warehouse_2",
  "Cell1",
  "Cell2",
  "Press1",
  "Paint1",
  // vision dataset class names (must come from the API)
  "scratch",
  "crack",
  "rust",
];

// Real values computed during earlier verifications. They must never appear in
// the frontend source.
const FORBIDDEN_VALUE_LITERALS = [
  "4072.86",
  "814572",
  "99.435",
  "83.718",
  "0.7759",
  "423931",
  "605620",
];

const FORBIDDEN_PATTERNS: Array<{ name: string; pattern: RegExp }> = [
  { name: "currency-symbol with magnitude", pattern: /[$€£¥₹]\s?\d[\d,.]*/ },
  { name: "hardcoded confidence percentage", pattern: /\bconfidence\b\s*[:=]\s*\d/i },
  { name: "hardcoded defect class", pattern: /defect_class\s*[:=]\s*["']/i },
  { name: "fake live telemetry", pattern: /Math\.random\(\)/ },
];

function collectSourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      if (entry === "tests") continue;
      collectSourceFiles(full, out);
    } else if (/\.(ts|tsx)$/.test(entry) && !full.endsWith(".test.ts") && !full.endsWith(".test.tsx")) {
      out.push(full);
    }
  }
  return out;
}

describe("static-data guard", () => {
  const files = collectSourceFiles(SRC);

  it("scans a meaningful number of source files", () => {
    expect(files.length).toBeGreaterThan(8);
  });

  it("contains no hardcoded dataset station names", () => {
    for (const file of files) {
      const content = readFileSync(file, "utf8");
      for (const literal of FORBIDDEN_STATION_LITERALS) {
        const regex = new RegExp(`["'\`]${literal}["'\`]`);
        expect(regex.test(content), `${file} contains hardcoded station literal '${literal}'`).toBe(false);
      }
    }
  });

  it("contains no hardcoded result values from real runs", () => {
    for (const file of files) {
      const content = readFileSync(file, "utf8");
      for (const literal of FORBIDDEN_VALUE_LITERALS) {
        expect(content.includes(literal), `${file} contains hardcoded result value '${literal}'`).toBe(false);
      }
    }
  });

  it("contains no forbidden result patterns", () => {
    for (const file of files) {
      const content = readFileSync(file, "utf8");
      for (const { name, pattern } of FORBIDDEN_PATTERNS) {
        expect(pattern.test(content), `${file} matches forbidden pattern '${name}'`).toBe(false);
      }
    }
  });

  it("does not ship mock result modules", () => {
    for (const file of files) {
      expect(/mockData|fixtures\/results|sampleResults/i.test(file)).toBe(false);
    }
  });
});
