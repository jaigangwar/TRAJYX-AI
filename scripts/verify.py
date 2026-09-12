"""Run every check across the monorepo and print one summary.

    python scripts/verify.py              # everything available
    python scripts/verify.py --only web   # one component
    python scripts/verify.py --list       # show the check list

Exits non-zero if any check fails, so it doubles as the CI entry point.
Checks whose toolchain is not installed are reported as SKIPPED rather than
failed, so a contributor without Flutter can still verify the Python and web
tiers.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PYTHON = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

OK = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


@dataclass
class Check:
    component: str
    name: str
    command: list[str]
    cwd: Path
    #: Executable that must be on PATH for this check to be possible.
    requires: str | None = None


def build_checks() -> list[Check]:
    web = ROOT / "web"
    mobile = ROOT / "mobile"
    backend = ROOT / "backend"

    return [
        Check("contracts", "generated bindings are current",
              [PYTHON, "scripts/gen_contracts.py", "--check"], ROOT),
        Check("backend", "ruff lint",
              [PYTHON, "-m", "ruff", "check", "backend", "cv", "ml", "scripts", "tests"], ROOT),
        Check("backend", "pytest",
              [PYTHON, "-m", "pytest", "-q"], backend),
        Check("cv", "pytest",
              [PYTHON, "-m", "pytest", "tests/cv", "-q"], ROOT),
        Check("web", "oxlint", ["npm", "run", "--silent", "lint"], web, requires="npm"),
        Check("web", "typecheck", ["npm", "run", "--silent", "typecheck"], web, requires="npm"),
        Check("web", "vitest", ["npm", "run", "--silent", "test"], web, requires="npm"),
        Check("web", "production build", ["npm", "run", "--silent", "build"], web, requires="npm"),
        Check("mobile", "dart analyze", ["flutter", "analyze"], mobile, requires="flutter"),
        Check("mobile", "flutter test", ["flutter", "test"], mobile, requires="flutter"),
    ]


def run(check: Check) -> tuple[str, float, str]:
    if check.requires and shutil.which(check.requires) is None:
        return SKIP, 0.0, f"{check.requires} is not on PATH"
    if not check.cwd.exists():
        return SKIP, 0.0, f"{check.cwd.relative_to(ROOT)} does not exist yet"

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            check.command,
            cwd=check.cwd,
            capture_output=True,
            text=True,
            timeout=1800,
            shell=os.name == "nt" and check.command[0] in {"npm", "flutter"},
        )
    except subprocess.TimeoutExpired:
        return FAIL, time.perf_counter() - started, "timed out after 1800s"
    except FileNotFoundError as error:
        return SKIP, time.perf_counter() - started, str(error)

    elapsed = time.perf_counter() - started
    if completed.returncode == 0:
        return OK, elapsed, ""

    # Keep the tail: test runners put the useful summary at the end.
    output = (completed.stdout + completed.stderr).strip().splitlines()
    return FAIL, elapsed, "\n".join(output[-25:])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all TRAJYX checks.")
    parser.add_argument("--only", action="append", metavar="COMPONENT",
                        help="limit to a component (contracts, backend, cv, web, mobile)")
    parser.add_argument("--list", action="store_true", help="list checks and exit")
    args = parser.parse_args()

    checks = build_checks()
    if args.only:
        wanted = {component.lower() for component in args.only}
        checks = [check for check in checks if check.component in wanted]
        if not checks:
            print(f"No checks match {sorted(wanted)}", file=sys.stderr)
            return 2

    if args.list:
        for check in checks:
            print(f"{check.component:10} {check.name}")
        return 0

    print(f"TRAJYX verify - {len(checks)} checks - python {PYTHON}\n")

    results: list[tuple[Check, str, float, str]] = []
    for check in checks:
        label = f"{check.component}: {check.name}"
        print(f"  running  {label} ... ", end="", flush=True)
        status, elapsed, detail = run(check)
        print(f"{status} ({elapsed:.1f}s)")
        results.append((check, status, elapsed, detail))

    failures = [entry for entry in results if entry[1] == FAIL]
    skipped = [entry for entry in results if entry[1] == SKIP]

    print("\n" + "=" * 74)
    passed = sum(1 for entry in results if entry[1] == OK)
    print(f"{passed} passed, {len(failures)} failed, {len(skipped)} skipped")

    for check, _status, _elapsed, detail in skipped:
        print(f"\nSKIPPED  {check.component}: {check.name}\n  {detail}")

    for check, _status, _elapsed, detail in failures:
        print(f"\nFAILED   {check.component}: {check.name}")
        print("  " + "\n  ".join(detail.splitlines()))

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
