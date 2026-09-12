"""TRAJYX computer-vision pipeline.

Layout mirrors the stages of the analysis:

    video/        decoding, frame sampling, annotated output
    detection/    per-frame object detection behind the Detector protocol
    tracking/     persistent identities behind the Tracker protocol
    trajectory/   smoothing, speed and heading estimation
    violations/   modular safety and violation detectors
    interactions/ pairwise conflict analysis, TTC, near misses

Every stage depends on the protocol of the stage before it, never on a
concrete implementation, so any single stage can be replaced independently.
"""

from trajyx_cv.types import (  # noqa: F401
    BoundingBox,
    Detection,
    FrameMeta,
    Point,
    Track,
    TrackPoint,
)

__version__ = "0.1.0"
