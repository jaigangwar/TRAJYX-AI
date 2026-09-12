"""Ultralytics YOLO detector behind the Detector protocol."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from trajyx_cv.detection.base import COCO_TO_VEHICLE_CLASS, DetectorInfo, map_detector_class
from trajyx_cv.types import BoundingBox, Detection, FrameMeta
from trajyx_shared.domain import VehicleClass

log = logging.getLogger(__name__)


class ModelUnavailableError(RuntimeError):
    """Raised when weights or torch are missing.

    Raised rather than degrading silently: a pipeline that quietly produced no
    detections would look like a road with no traffic on it.
    """


class YoloDetector:
    """YOLO detection with COCO-to-TRAJYX class mapping.

    Weights are resolved in order: an explicit path, then `models/weights/`,
    then the Ultralytics default (which downloads `yolov8n.pt` on first use).
    """

    def __init__(
        self,
        weights: str | Path = "yolov8n.pt",
        *,
        confidence: float = 0.30,
        iou: float = 0.5,
        device: str = "cpu",
        image_size: int = 640,
        class_mapping: dict[str, VehicleClass] | None = None,
    ) -> None:
        self._confidence = confidence
        self._iou = iou
        self._device = device
        self._image_size = image_size
        self._mapping = class_mapping or COCO_TO_VEHICLE_CLASS
        self._unmapped: dict[str, int] = {}

        try:
            from ultralytics import YOLO
        except ImportError as error:
            raise ModelUnavailableError(
                "ultralytics is not installed. Install cv/requirements.txt on machines "
                "that run analysis."
            ) from error

        weights_path = Path(weights)
        if not weights_path.is_absolute() and not weights_path.exists():
            bundled = Path(__file__).resolve().parents[3] / "models" / "weights" / weights_path.name
            if bundled.exists():
                weights_path = bundled

        try:
            self._model: Any = YOLO(str(weights_path))
        except Exception as error:  # noqa: BLE001 - any load failure is fatal here
            raise ModelUnavailableError(
                f"Could not load YOLO weights {weights_path!r}: {error}"
            ) from error

        self._names: dict[int, str] = dict(self._model.names or {})
        self._info = DetectorInfo(
            name="ultralytics-yolo",
            version=f"{weights_path.stem}-1.0",
            classes=tuple(sorted(set(self._mapping.values()), key=lambda item: item.value)),
            input_size=(image_size, image_size),
            device=device,
        )
        self.last_inference_ms: float | None = None

    @property
    def info(self) -> DetectorInfo:
        return self._info

    @property
    def unmapped_labels(self) -> dict[str, int]:
        """Detector labels with no TRAJYX mapping, and how often they appeared.

        A rise here means the weights and the mapping have drifted apart, so it
        is reported rather than silently dropped.
        """
        return dict(self._unmapped)

    def warmup(self) -> None:
        blank = np.zeros((self._image_size, self._image_size, 3), dtype=np.uint8)
        self._model.predict(blank, verbose=False, device=self._device, imgsz=self._image_size)

    def detect(self, frame: np.ndarray, meta: FrameMeta) -> list[Detection]:
        return self.detect_batch([frame], [meta])[0]

    def detect_batch(
        self, frames: Sequence[np.ndarray], metas: Sequence[FrameMeta]
    ) -> list[list[Detection]]:
        if len(frames) != len(metas):
            raise ValueError("frames and metas must be the same length")
        if not frames:
            return []

        started = time.perf_counter()
        results = self._model.predict(
            list(frames),
            conf=self._confidence,
            iou=self._iou,
            device=self._device,
            imgsz=self._image_size,
            verbose=False,
        )
        self.last_inference_ms = (time.perf_counter() - started) * 1000 / len(frames)

        return [self._convert(result, meta) for result, meta in zip(results, metas, strict=True)]

    def _convert(self, result: Any, meta: FrameMeta) -> list[Detection]:
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []

        xyxy = boxes.xyxy.cpu().numpy()
        confidences = boxes.conf.cpu().numpy()
        class_ids = boxes.cls.cpu().numpy().astype(int)

        detections: list[Detection] = []
        for index in range(len(class_ids)):
            raw_name = self._names.get(int(class_ids[index]), str(class_ids[index]))
            mapped = map_detector_class(raw_name, self._mapping)
            if mapped is None:
                self._unmapped[raw_name] = self._unmapped.get(raw_name, 0) + 1
                continue

            x1, y1, x2, y2 = (float(value) for value in xyxy[index])
            box = BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2).clip_to(meta.width, meta.height)
            if box.area <= 1.0:
                continue

            detections.append(
                Detection(
                    vehicle_class=mapped,
                    confidence=float(min(1.0, max(0.0, confidences[index]))),
                    box=box,
                    frame_index=meta.index,
                    timestamp_s=meta.timestamp_s,
                    raw_class_name=raw_name,
                )
            )
        return detections
