"""Evaluate a trained model against its named, segment/time-held-out corpus."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, precision_recall_fscore_support, r2_score
from xgboost import XGBRegressor

from trajyx_ml.features.build import FEATURE_NAMES
from trajyx_ml.training.split import segment_time_split

UTC = timezone.utc


def _risk_band(score: float) -> str:
    if score <= 25:
        return "LOW"
    if score <= 50:
        return "MODERATE"
    if score <= 75:
        return "HIGH"
    return "CRITICAL"


def evaluate(dataset_path: Path, artifact_dir: Path) -> dict[str, Any]:
    model_path = artifact_dir / "model.json"
    metadata_path = artifact_dir / "metadata.json"
    if not model_path.is_file() or not metadata_path.is_file():
        raise FileNotFoundError(f"model.json and metadata.json are required in {artifact_dir}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    frame = pd.read_csv(dataset_path)
    required = {"dataset_version", "segment_id", "window_start", "target_risk_score", *FEATURE_NAMES}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"dataset is missing columns: {', '.join(sorted(missing))}")
    versions = frame["dataset_version"].dropna().astype(str).unique()
    if len(versions) != 1 or str(versions[0]) != metadata.get("dataset_version"):
        raise ValueError("evaluation dataset_version must match the version used to train this artifact")
    frame["target_risk_score"] = pd.to_numeric(frame["target_risk_score"], errors="coerce")
    frame = frame.dropna(subset=["target_risk_score", "segment_id", "window_start"])
    if ((frame["target_risk_score"] < 0) | (frame["target_risk_score"] > 100)).any():
        raise ValueError("target_risk_score values must be within 0..100")
    train_rows, test_rows, cutoff = segment_time_split(frame)
    if metadata.get("time_cutoff_utc") != cutoff:
        raise ValueError("dataset split differs from training metadata; use the unchanged versioned dataset")

    model = XGBRegressor()
    model.load_model(model_path)
    actual = test_rows["target_risk_score"].to_numpy(dtype=float)
    predicted = np.clip(model.predict(test_rows[list(FEATURE_NAMES)]), 0, 100)
    actual_bands = [_risk_band(value) for value in actual]
    predicted_bands = [_risk_band(value) for value in predicted]
    labels = ["LOW", "MODERATE", "HIGH", "CRITICAL"]
    precision, recall, f1, _ = precision_recall_fscore_support(
        actual_bands, predicted_bands, labels=labels, average="macro", zero_division=0
    )
    band_calibration = {}
    for band in labels:
        mask = np.array([value == band for value in actual_bands])
        band_calibration[band] = {
            "samples": int(mask.sum()),
            "actual_mean": round(float(actual[mask].mean()), 3) if mask.any() else None,
            "predicted_mean": round(float(predicted[mask].mean()), 3) if mask.any() else None,
        }
    result: dict[str, Any] = {
        "name": metadata["name"],
        "version": artifact_dir.name,
        "dataset_version": str(versions[0]),
        "evaluated_at": datetime.now(UTC).isoformat(),
        "split": {
            "strategy": "segment-held-out and future-time-held-out",
            "time_cutoff_utc": cutoff,
            "train_rows": len(train_rows),
            "test_rows": len(test_rows),
            "train_segments": int(train_rows["segment_id"].nunique()),
            "test_segments": int(test_rows["segment_id"].nunique()),
        },
        "metrics": {
            "mae": round(float(mean_absolute_error(actual, predicted)), 4),
            "rmse": round(float(np.sqrt(mean_squared_error(actual, predicted))), 4),
            "r2": round(float(r2_score(actual, predicted)), 4)
            if len(actual) >= 2 and float(np.var(actual)) > 0 else None,
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1": round(float(f1), 4),
            "band_calibration": band_calibration,
        },
        "labels": "Human-reviewed risk scores and derived risk bands; never heuristic pseudo-labels.",
    }
    (artifact_dir / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    metadata["evaluation"] = result
    metadata["metrics"] = result["metrics"]
    metadata["evaluated_at"] = result["evaluated_at"]
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.dataset, args.artifact)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
