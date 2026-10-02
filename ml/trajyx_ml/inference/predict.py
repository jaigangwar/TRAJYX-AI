"""Load a versioned risk model for inference, or report an unloaded state."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from trajyx_ml.features.build import FEATURE_NAMES


class RiskPredictor:
    def __init__(self, artifact_dir: Path) -> None:
        self.artifact_dir = artifact_dir
        self.model: Any | None = None
        self.metadata: dict[str, Any] | None = None
        model_path, metadata_path = artifact_dir / "model.json", artifact_dir / "metadata.json"
        if not model_path.is_file() or not metadata_path.is_file():
            return
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("feature_names") != list(FEATURE_NAMES):
            raise ValueError("artifact feature contract does not match this application version")
        from xgboost import XGBRegressor

        model = XGBRegressor()
        model.load_model(model_path)
        self.model = model
        self.metadata = metadata

    def predict(self, features: dict[str, float]) -> dict[str, Any]:
        if self.model is None or self.metadata is None:
            return {"available": False, "reason": "No evaluated risk model artifact is loaded."}
        missing = set(FEATURE_NAMES) - set(features)
        if missing:
            raise ValueError(f"feature row is missing: {', '.join(sorted(missing))}")
        values = [float(features[name]) for name in FEATURE_NAMES]
        if any(math.isinf(value) for value in values):
            raise ValueError("feature values may be finite or NaN, but not infinity")
        score = float(self.model.predict([values])[0])
        return {
            "available": True,
            "score": round(min(100.0, max(0.0, score)), 2),
            "model_name": self.metadata["name"],
            "model_version": self.artifact_dir.name,
            "dataset_version": self.metadata.get("dataset_version"),
            "evaluated_at": self.metadata.get("evaluated_at"),
        }
