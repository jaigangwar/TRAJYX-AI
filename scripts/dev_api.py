"""Start the TRAJYX API in development, with reload.

    python scripts/dev_api.py
    python scripts/dev_api.py --port 8001 --log-level DEBUG

Uses the repository virtualenv when one exists, so it works without the venv
being activated in the calling shell.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the TRAJYX API with autoreload.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-level", default=None, help="overrides TRAJYX_LOG_LEVEL")
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()

    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    if not VENV_PYTHON.exists():
        print(
            "Warning: .venv not found, falling back to the current interpreter.\n"
            "Create it with:  py -3.10 -m venv .venv",
            file=sys.stderr,
        )

    command = [
        python,
        "-m",
        "uvicorn",
        "app.main:app",
        "--app-dir",
        str(ROOT / "backend"),
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if not args.no_reload:
        # Watch the backend and the shared contract, but not data/ or node_modules.
        command += ["--reload", "--reload-dir", str(ROOT / "backend"), "--reload-dir", str(ROOT / "shared")]

    env = os.environ.copy()
    if args.log_level:
        env["TRAJYX_LOG_LEVEL"] = args.log_level.upper()

    print(f"TRAJYX API  http://{args.host}:{args.port}   docs: /docs\n")
    try:
        return subprocess.call(command, cwd=ROOT, env=env)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
