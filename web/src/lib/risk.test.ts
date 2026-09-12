import { describe, expect, it } from "vitest";

import { RISK_LEVELS_ASCENDING, compareRiskLevel, riskLevelFromScore, riskPresentation } from "@/lib/risk";
import { RISK_BANDS } from "@shared/domain";

describe("risk banding", () => {
  it("maps each documented band boundary to the right level", () => {
    // Boundaries are the values most likely to regress.
    expect(riskLevelFromScore(0)).toBe("LOW");
    expect(riskLevelFromScore(25)).toBe("LOW");
    expect(riskLevelFromScore(26)).toBe("MODERATE");
    expect(riskLevelFromScore(50)).toBe("MODERATE");
    expect(riskLevelFromScore(51)).toBe("HIGH");
    expect(riskLevelFromScore(75)).toBe("HIGH");
    expect(riskLevelFromScore(76)).toBe("CRITICAL");
    expect(riskLevelFromScore(100)).toBe("CRITICAL");
  });

  it("clamps scores outside 0-100 rather than throwing", () => {
    expect(riskLevelFromScore(-40)).toBe("LOW");
    expect(riskLevelFromScore(999)).toBe("CRITICAL");
  });

  it("agrees with the generated contract bands", () => {
    for (const band of RISK_BANDS) {
      expect(riskLevelFromScore(band.min)).toBe(band.level);
      expect(riskLevelFromScore(band.max)).toBe(band.level);
    }
  });

  it("covers the whole 0-100 range with no gaps", () => {
    for (let score = 0; score <= 100; score += 1) {
      expect(RISK_LEVELS_ASCENDING).toContain(riskLevelFromScore(score));
    }
  });
});

describe("risk presentation", () => {
  it("provides a distinct colour and a text label for every level", () => {
    const colors = new Set<string>();
    for (const level of RISK_LEVELS_ASCENDING) {
      const presentation = riskPresentation(level);
      expect(presentation.label).toBeTruthy();
      colors.add(presentation.color);
    }
    // Colour must never be the sole carrier of meaning, but it must still differ.
    expect(colors.size).toBe(RISK_LEVELS_ASCENDING.length);
  });

  it("orders levels from least to most severe", () => {
    expect(compareRiskLevel("LOW", "CRITICAL")).toBeLessThan(0);
    expect(compareRiskLevel("CRITICAL", "LOW")).toBeGreaterThan(0);
    expect(compareRiskLevel("HIGH", "HIGH")).toBe(0);
  });
});
