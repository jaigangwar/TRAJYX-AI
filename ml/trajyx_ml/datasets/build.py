"""Build a versioned CSV from human-reviewed, labelled window records."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from trajyx_ml.features.build import FEATURE_NAMES, build_feature_row


def build_rows(source: Path, dataset_version: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with source.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"line {line_number}: expected a JSON object")
            if record.get("dataset_version") != dataset_version:
                raise ValueError(f"line {line_number}: dataset_version does not match the requested version")
            segment = record.get("segment")
            if not isinstance(segment, dict) or not segment.get("id"):
                raise ValueError(f"line {line_number}: a segment with an id is required")
            label = record.get("target_risk_score")
            if isinstance(label, bool) or not isinstance(label, int | float) or not 0 <= float(label) <= 100:
                raise ValueError(f"line {line_number}: target_risk_score must be a reviewed value from 0 to 100")
            start = datetime.fromisoformat(str(record["window_start"]).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(record["window_end"]).replace("Z", "+00:00"))
            features = build_feature_row(
                segment=segment,
                events=record.get("events", []),
                analyses=record.get("analyses", []),
                window_start=start,
                window_end=end,
            )
            rows.append({
                "dataset_version": dataset_version,
                "segment_id": str(segment["id"]),
                "window_start": start.isoformat(),
                "target_risk_score": float(label),
                **features,
            })
    if not rows:
        raise ValueError("no labelled windows found")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSONL of reviewed windows and source records")
    parser.add_argument("--dataset-version", required=True, help="Immutable id for this labelled corpus")
    parser.add_argument("--output", type=Path, required=True, help="Destination CSV for training")
    args = parser.parse_args()
    rows = build_rows(args.input, args.dataset_version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    columns = ["dataset_version", "segment_id", "window_start", "target_risk_score", *FEATURE_NAMES]
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Built {len(rows)} labelled windows for {args.dataset_version}: {args.output}")


if __name__ == "__main__":
    main()
