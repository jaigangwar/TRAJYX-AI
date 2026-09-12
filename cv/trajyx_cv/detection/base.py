"""Detector interface and class mapping.

The pipeline depends on the ``Detector`` protocol, never on Ultralytics
directly, so a YOLO release, an ONNX export or a different architecture can be
swapped in without touching the analysis stages. Phase 4 supplies the YOLO
implementation behind this interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

import numpy as np

from trajyx_cv.types import Detection, FrameMeta
from trajyx_shared.domain import VehicleClass


@dataclass(frozen=True, slots=True)
class DetectorInfo:
    """Provenance of a detector, recorded on every event it contributes to.

    Without this, a stored detection cannot be traced back to the weights that
    produced it, which makes measured metrics unattributable.
    """

    name: str
    version: str
    """Model version string, e.g. ``yolov8n-1.0``. Written to events as
    ``model_version`` so results stay attributable."""

    classes: tuple[VehicleClass, ...]
    """Classes this detector can actually emit. A class absent here is reported
    as unavailable rather than as zero occurrences."""

    input_size: tuple[int, int] | None = None
    device: str = "cpu"


@runtime_checkable
class Detector(Protocol):
    """Detects objects in single frames or batches."""

    @property
    def info(self) -> DetectorInfo: ...

    def detect(self, frame: np.ndarray, meta: FrameMeta) -> list[Detection]:
        """Detect objects in one BGR frame.

        Args:
            frame: ``(height, width, 3)`` uint8 array in BGR channel order,
                as produced by OpenCV.
            meta: Identity and timing of the frame, copied onto each detection.

        Returns:
            Detections above the detector's confidence threshold. An empty list
            means "nothing detected", which is distinct from a failure — those
            raise.
        """
        ...

    def detect_batch(self, frames: Sequence[np.ndarray], metas: Sequence[FrameMeta]) -> list[list[Detection]]:
        """Detect over a batch, one result list per input frame.

        Batching is what makes GPU inference worthwhile; implementations without
        a batch path should loop over :meth:`detect`.
        """
        ...

    def warmup(self) -> None:
        """Run one throwaway inference pass.

        The first inference on a cold model is several times slower than steady
        state. Calling this before timing avoids attributing that cost to the
        first frames of a video.
        """
        ...


# COCO is what the stock YOLO weights are trained on, and it is the starting
# point before a traffic-specific model is fine-tuned. Classes TRAJYX cares
# about that COCO does not distinguish — scooter versus motorcycle, and
# auto-rickshaw — are absent on purpose: mapping them here would invent a
# capability the weights do not have. They become available once a model
# trained on them is registered, and until then the safety engine reports
# UNABLE_TO_DETERMINE rather than guessing.
COCO_TO_VEHICLE_CLASS: dict[str, VehicleClass] = {
    "car": VehicleClass.CAR,
    "motorcycle": VehicleClass.MOTORCYCLE,
    "bus": VehicleClass.BUS,
    "truck": VehicleClass.TRUCK,
    "bicycle": VehicleClass.BICYCLE,
    "person": VehicleClass.PEDESTRIAN,
}

#: COCO classes deliberately dropped: they are not road users, and keeping them
#: would inflate traffic counts.
COCO_IGNORED = frozenset(
    {"traffic light", "stop sign", "fire hydrant", "parking meter", "bench", "train", "boat"}
)


def map_detector_class(raw_name: str, mapping: dict[str, VehicleClass] | None = None) -> VehicleClass | None:
    """Translate a detector's own label into the shared taxonomy.

    Returns ``None`` for a label with no mapping, which the caller should count
    as an unmapped detection rather than silently discard — a sudden rise in
    unmapped labels means the weights and the mapping have drifted apart.
    """
    table = mapping if mapping is not None else COCO_TO_VEHICLE_CLASS
    return table.get(raw_name.strip().lower())
