"""Train and version the XGBoost risk regressor from reviewed labels."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from xgboost import XGBRegressor

from trajyx_ml.features.build import FEATURE_NAMES
from trajyx_ml.training.split import segment_time_split

PARAMETERS = {
    "n_estimators": 400,
    "max_depth": 4,
    "learning_rate": 0.035,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "objective": "reg:squarederror",
    "random_state": 42,
    "n_jobs": 4,
}


def train(dataset_path: Path, artifact_dir: Path) -> Path:
    frame = pd.read_csv(dataset_path)
    required = {"dataset_version", "segment_id", "window_start", "target_risk_score", *FEATURE_NAMES}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"dataset is missing columns: {', '.join(sorted(missing))}")
    versions = frame["dataset_version"].dropna().astype(str).unique()
    if len(versions) != 1:
        raise ValueError("training requires one named dataset_version per run")
    frame["target_risk_score"] = pd.to_numeric(frame["target_risk_score"], errors="coerce")
    frame = frame.dropna(subset=["target_risk_score", "segment_id", "window_start"])
    if ((frame["target_risk_score"] < 0) | (frame["target_risk_score"] > 100)).any():
        raise ValueError("target_risk_score values must be within 0..100")
    train_rows, test_rows, cutoff = segment_time_split(frame)
    model = XGBRegressor(**PARAMETERS)
    model.fit(train_rows[list(FEATURE_NAMES)], train_rows["target_risk_score"])

    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / "model.json"
    model.save_model(model_path)
    metadata = {
        "name": "trajyx-risk-xgb",
        "artifact_format": "xgboost-json",
        "dataset_version": str(versions[0]),
        "created_at": datetime.now(UTC).isoformat(),
        "feature_names": list(FEATURE_NAMES),
        "target": "human-reviewed risk score, 0..100",
        "train_rows": len(train_rows),
        "heldout_rows": len(test_rows),
        "train_segments": int(train_rows["segment_id"].nunique()),
        "heldout_segments": int(test_rows["segment_id"].nunique()),
        "time_cutoff_utc": cutoff,
        "hyperparameters": PARAMETERS,
        "metrics": None,
        "note": "Metrics remain unavailable until the separate evaluation command completes.",
    }
    (artifact_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return model_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="CSV produced by trajyx_ml.datasets.build")
    parser.add_argument("--output", type=Path, required=True, help="Versioned model artifact directory")
    args = parser.parse_args()
    print(f"Saved model: {train(args.dataset, args.output)}")


if __name__ == "__main__":
    main()
