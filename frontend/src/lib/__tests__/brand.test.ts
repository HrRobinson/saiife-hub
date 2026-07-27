import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// Vitest runs this as ESM, so `__dirname` does not exist.
const HERE = dirname(fileURLToPath(import.meta.url));
const UI_SRC = join(HERE, "../../../../packages/ui/src");

describe("brand layer", () => {
  it("ships the brand tokens copied from saiife.com-old", () => {
    const tokens = readFileSync(join(UI_SRC, "tokens.css"), "utf8");
    expect(tokens).toContain("--brand-from");
    expect(tokens).toContain("--brand-to");
    expect(tokens).toContain("--border-glow");
  });

  it("ships the brand primitives", () => {
    for (const file of [
      "GradientButton.tsx",
      "Eyebrow.tsx",
      "RingIconBadge.tsx",
      "SpotlightCard.tsx",
      "tailwind.preset.ts",
    ]) {
      expect(() => readFileSync(join(UI_SRC, file), "utf8")).not.toThrow();
    }
  });

  it("exports the brand primitives from the package entry point", () => {
    const index = readFileSync(join(UI_SRC, "index.ts"), "utf8");
    for (const name of ["GradientButton", "Eyebrow", "RingIconBadge", "SpotlightCard"]) {
      expect(index).toContain(name);
    }
  });

  it("wires the ClashDisplay face into globals.css via --font-display", () => {
    const globals = readFileSync(join(HERE, "../../app/globals.css"), "utf8");
    expect(globals).toContain("--font-display");
    expect(globals).toContain("@saiife/ui/tokens.css");
    expect(globals).toContain('@source "../../../packages/ui/src"');
  });

  it("no longer reaches for @base-ui — the dead root-level duplicates are gone", () => {
    const index = readFileSync(join(UI_SRC, "index.ts"), "utf8");
    expect(index).not.toContain("LockedFeature");
    for (const dead of ["Button.tsx", "Badge.tsx", "Card.tsx", "Input.tsx", "Label.tsx"]) {
      expect(() => readFileSync(join(UI_SRC, dead), "utf8")).toThrow();
    }
  });
});
