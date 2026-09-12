"""Tracker interface.

Tracking is what turns per-frame detections into objects with history, and
history is what makes behaviour analysis possible: speed, wrong-way movement,
hard braking and near misses all require knowing that the car in frame 40 is
the same car as in frame 12.

The pipeline depends on this protocol, not on a specific tracker. Phase 5
supplies the ByteTrack implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from trajyx_cv.types import Detection, FrameMeta, Track


@dataclass(frozen=True, slots=True)
class TrackerInfo:
    name: str
    version: str


@dataclass(frozen=True, slots=True)
class TrackerConfig:
    """Tuning shared by association-based trackers.

    Defaults are ByteTrack's published values, which behave reasonably on
    fixed-camera traffic footage. They are exposed rather than hardcoded
    because a 15 fps camera and a 60 fps camera need different buffers.
    """

    track_activation_threshold: float = 0.25
    """Minimum detection confidence to start a new track. Low by design:
    ByteTrack's strength is recovering low-confidence detections that belong to
    an existing track."""

    lost_track_buffer_frames: int = 30
    """How long a track survives without a match before being dropped. Should
    be roughly one second of frames, so scale it with the source frame rate."""

    minimum_matching_threshold: float = 0.25
    """Minimum **IoU** to associate a detection with an existing track.

    Note this is an IoU *score*, not ByteTrack's published ``match_thresh`` of
    0.8 — that figure is a threshold on a cost matrix of ``1 - IoU``, i.e. it
    accepts IoU >= 0.2. Using 0.8 as a raw IoU score rejects any vehicle moving
    more than a few pixels per frame, which breaks identity on exactly the
    fast-moving traffic this system exists to analyse.
    """

    second_pass_threshold: float = 0.15
    """Relaxed IoU for the low-confidence rescue pass. Lower because a
    partially occluded box overlaps its prediction less."""

    frame_rate: float = 25.0
    """Source frame rate, after any frame-stride sampling. Buffers are
    expressed in frames, so this must reflect what the tracker actually sees."""

    minimum_consecutive_frames: int = 3
    """Frames a track must be confirmed for before it is reported. Filters out
    single-frame false positives that would otherwise become phantom
    vehicles in the counts."""


@runtime_checkable
class Tracker(Protocol):
    """Assigns persistent identities to per-frame detections."""

    @property
    def info(self) -> TrackerInfo: ...

    def update(self, detections: list[Detection], meta: FrameMeta) -> list[Track]:
        """Associate one frame's detections with existing tracks.

        Must be called once per frame in presentation order; association
        depends on temporal continuity, so skipping or reordering frames
        degrades identity persistence.

        Returns:
            The tracks confirmed in this frame, each carrying its history up to
            and including this frame. Tracks that were not matched in this
            frame are absent from the result but retained internally until the
            lost-track buffer expires.
        """
        ...

    def finalize(self) -> list[Track]:
        """Flush all tracks, including those still inside the lost buffer.

        Called once at end of video to get the complete set for trajectory and
        interaction analysis.
        """
        ...

    def reset(self) -> None:
        """Clear all state.

        Track ids are per-video, so this must be called between videos to keep
        identities from leaking across analyses.
        """
        ...
