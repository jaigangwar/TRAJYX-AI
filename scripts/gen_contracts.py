"""Generate typed language bindings from the canonical domain contract.

Source of truth : shared/contracts/domain.json
Emits           : shared/ts/domain.ts                    (web)
                  shared/python/trajyx_shared/domain.py  (backend, cv, ml)
                  mobile/lib/core/contracts/domain.dart  (mobile)

Run after editing domain.json:  python scripts/gen_contracts.py
CI guard:                       python scripts/gen_contracts.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "shared" / "contracts" / "domain.json"

BANNER_LINES = [
    "TRAJYX generated file - DO NOT EDIT BY HAND.",
    "Source: shared/contracts/domain.json",
    "Regenerate: python scripts/gen_contracts.py",
]


def _camel(name: str) -> str:
    head, *tail = name.split("_")
    return head.lower() + "".join(p.capitalize() for p in tail)


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _alert_defaults(contract: dict) -> dict:
    return {k: v for k, v in contract["alert_thresholds"].items() if not k.startswith("$")}


# --------------------------------------------------------------------- TypeScript
def render_ts(c: dict) -> str:
    out: list[str] = ["/**"]
    out += [" * " + line for line in BANNER_LINES]
    out += [" */", "", 'export const CONTRACT_VERSION = "' + c["version"] + '";', ""]

    for name, spec in c["enums"].items():
        out.append("/** " + spec["doc"] + " */")
        out.append("export const " + name.upper() + "_VALUES = [")
        out += ['  "' + v + '",' for v in spec["values"]]
        out.append("] as const;")
        out.append("export type " + name + " = (typeof " + name.upper() + "_VALUES)[number];")
        out.append("")

    out.append("export interface RiskBand { level: RiskLevel; min: number; max: number }")
    out.append("export const RISK_BANDS: readonly RiskBand[] = [")
    for b in c["risk_bands"]:
        out.append('  { level: "' + b["level"] + '", min: ' + str(b["min"]) + ", max: " + str(b["max"]) + " },")
    out.append("] as const;")
    out.append("")

    out.append("export interface TtcBandSpec { band: TtcBand; minSeconds: number; maxSeconds: number | null }")
    out.append("export const TTC_BANDS: readonly TtcBandSpec[] = [")
    for b in c["ttc_bands"]:
        mx = "null" if b["max_seconds"] is None else str(b["max_seconds"])
        out.append('  { band: "' + b["band"] + '", minSeconds: ' + str(b["min_seconds"]) + ", maxSeconds: " + mx + " },")
    out.append("] as const;")
    out.append("")

    out.append("export const EVENT_CATEGORY: Readonly<Record<EventType, EventCategory>> = {")
    for k, v in c["event_category_map"].items():
        out.append("  " + k + ': "' + v + '",')
    out.append("};")
    out.append("")

    out.append("export const COLLECTIONS = {")
    for col in c["collections"]:
        out.append("  " + _camel(col) + ': "' + col + '",')
    out.append("} as const;")
    out.append("")

    out.append("export const ALERT_DEFAULTS = " + json.dumps(_alert_defaults(c), indent=2) + " as const;")
    out.append("")
    out.append("/** Map a 0-100 risk score onto its band. Scores are clamped into range. */")
    out.append("export function riskLevelFromScore(score: number): RiskLevel {")
    out.append("  const s = Math.max(0, Math.min(100, score));")
    out.append("  for (const band of RISK_BANDS) if (s <= band.max) return band.level;")
    out.append('  return "CRITICAL";')
    out.append("}")
    out.append("")
    return "\n".join(out)


# ------------------------------------------------------------------------- Python
def render_py(c: dict) -> str:
    out = ['"""']
    out += BANNER_LINES
    out += ['"""', "", "from __future__ import annotations", "", "from enum import Enum", "from typing import Final", ""]
    out.append('CONTRACT_VERSION: Final[str] = "' + c["version"] + '"')
    out.append("")
    out.append("")

    for name, spec in c["enums"].items():
        out.append("class " + name + "(str, Enum):")
        out.append('    """' + spec["doc"] + '"""')
        out.append("")
        for v in spec["values"]:
            out.append("    " + v + ' = "' + v + '"')
        out.append("")
        out.append("")

    out.append("RISK_BANDS: Final[tuple[tuple[RiskLevel, int, int], ...]] = (")
    for b in c["risk_bands"]:
        out.append("    (RiskLevel." + b["level"] + ", " + str(b["min"]) + ", " + str(b["max"]) + "),")
    out.append(")")
    out.append("")

    out.append("TTC_BANDS: Final[tuple[tuple[TtcBand, float, float | None], ...]] = (")
    for b in c["ttc_bands"]:
        mx = "None" if b["max_seconds"] is None else repr(float(b["max_seconds"]))
        out.append("    (TtcBand." + b["band"] + ", " + repr(float(b["min_seconds"])) + ", " + mx + "),")
    out.append(")")
    out.append("")

    out.append("EVENT_CATEGORY: Final[dict[EventType, EventCategory]] = {")
    for k, v in c["event_category_map"].items():
        out.append("    EventType." + k + ": EventCategory." + v + ",")
    out.append("}")
    out.append("")

    out.append("COLLECTIONS: Final[dict[str, str]] = {")
    for col in c["collections"]:
        out.append('    "' + col + '": "' + col + '",')
    out.append("}")
    out.append("")

    out.append("ALERT_DEFAULTS: Final[dict] = " + json.dumps(_alert_defaults(c), indent=4))
    out.append("")
    out.append("")
    out.append("def risk_level_from_score(score: float) -> RiskLevel:")
    out.append('    """Map a 0-100 risk score onto its band. Scores are clamped into range."""')
    out.append("    s = max(0.0, min(100.0, float(score)))")
    out.append("    for level, _low, high in RISK_BANDS:")
    out.append("        if s <= high:")
    out.append("            return level")
    out.append("    return RiskLevel.CRITICAL")
    out.append("")
    out.append("")
    out.append("def ttc_band_from_seconds(seconds: float | None) -> TtcBand | None:")
    out.append('    """Band an ESTIMATED time-to-collision. None when TTC is undefined or negative."""')
    out.append("    if seconds is None or seconds < 0:")
    out.append("        return None")
    out.append("    for band, low, high in TTC_BANDS:")
    out.append("        if seconds >= low and (high is None or seconds < high):")
    out.append("            return band")
    out.append("    return TtcBand.LOW")
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------- Dart
def render_dart(c: dict) -> str:
    out = ["// " + line for line in BANNER_LINES]
    out += ["", "const String kContractVersion = '" + c["version"] + "';", ""]

    for name, spec in c["enums"].items():
        out.append("/// " + spec["doc"])
        out.append("enum " + name + " {")
        out += ["  " + _camel(v.lower()) + "('" + v + "')," for v in spec["values"]]
        out.append("  ;")
        out.append("")
        out.append("  const " + name + "(this.wire);")
        out.append("  final String wire;")
        out.append("")
        out.append("  static " + name + "? tryParse(String? value) {")
        out.append("    if (value == null) return null;")
        out.append("    for (final entry in " + name + ".values) {")
        out.append("      if (entry.wire == value) return entry;")
        out.append("    }")
        out.append("    return null;")
        out.append("  }")
        out.append("}")
        out.append("")

    out.append("class RiskBand {")
    out.append("  const RiskBand(this.level, this.min, this.max);")
    out.append("")
    out.append("  final RiskLevel level;")
    out.append("  final int min;")
    out.append("  final int max;")
    out.append("}")
    out.append("")
    out.append("const List<RiskBand> kRiskBands = [")
    for b in c["risk_bands"]:
        out.append(
            "  RiskBand(RiskLevel." + _camel(b["level"].lower()) + ", " + str(b["min"]) + ", " + str(b["max"]) + "),"
        )
    out.append("];")
    out.append("")
    out.append("/// Map a 0-100 risk score onto its band. Scores are clamped into range.")
    out.append("RiskLevel riskLevelFromScore(num score) {")
    out.append("  final s = score.clamp(0, 100);")
    out.append("  for (final band in kRiskBands) {")
    out.append("    if (s <= band.max) return band.level;")
    out.append("  }")
    out.append("  return RiskLevel.critical;")
    out.append("}")
    out.append("")
    return "\n".join(out)


TARGETS = [
    (Path("shared/ts/domain.ts"), render_ts),
    (Path("shared/python/trajyx_shared/domain.py"), render_py),
    (Path("mobile/lib/core/contracts/domain.dart"), render_dart),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate TRAJYX domain contract bindings.")
    parser.add_argument("--check", action="store_true", help="verify outputs are current; write nothing")
    args = parser.parse_args()

    contract = load_contract()
    stale: list[str] = []

    for rel, render in TARGETS:
        path = ROOT / rel
        content = render(contract)
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == content:
            continue
        if args.check:
            stale.append(str(rel).replace("\\", "/"))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        print("wrote " + str(rel).replace("\\", "/"))

    if stale:
        print("Stale generated contracts: " + ", ".join(stale), file=sys.stderr)
        print("Run: python scripts/gen_contracts.py", file=sys.stderr)
        return 1
    if args.check:
        print("contracts up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
