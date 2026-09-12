"""ByteTrack-style multi-object tracker.

Implemented directly rather than pulled from a library for two reasons: it is
about 200 lines, and the TRAJYX pipeline needs the tracker to emit
:class:`Track` objects carrying TRAJYX classes and per-frame history, which a
generic tracker does not.

ByteTrack's idea, which is what makes it worth using here: associate
high-confidence detections first, then give the *low*-confidence detections a
second chance to match tracks that are still unmatched. A partially occluded
vehicle at a busy junction drops to low confidence for a few frames, and
without that second pass its identity would break — which would silently
destroy the trajectory that wrong-way and near-miss detection depend on.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from trajyx_cv.tracking.base import TrackerConfig, TrackerInfo
from trajyx_cv.types import BoundingBox, Detection, FrameMeta, Track, TrackPoint
from trajyx_shared.domain import VehicleClass


@dataclass
class _TrackState:
    """Internal per-track bookkeeping."""

    track: Track
    #: Constant-velocity state: centre x, centre y, width, height, dx, dy.
    mean: np.ndarray
    hits: int = 1
    age: int = 0
    frames_since_update: int = 0
    confirmed: bool = False
    pending_points: list[TrackPoint] = field(default_factory=list)

    def predicted_box(self) -> BoundingBox:
        cx, cy, width, height, dx, dy = self.mean
        cx += dx
        cy += dy
        return BoundingBox(
            x1=cx - width / 2, y1=cy - height / 2, x2=cx + width / 2, y2=cy + height / 2
        )


def _to_state(box: BoundingBox) -> np.ndarray:
    centre = box.center
    return np.array([centre.x, centre.y, box.width, box.height, 0.0, 0.0], dtype=float)


def _iou_matrix(tracks: list[_TrackState], detections: list[Detection]) -> np.ndarray:
    matrix = np.zeros((len(tracks), len(detections)), dtype=float)
    for row, state in enumerate(tracks):
        predicted = state.predicted_box()
        for column, detection in enumerate(detections):
            matrix[row, column] = predicted.iou(detection.box)
    return matrix


def _greedy_match(
    scores: np.ndarray, threshold: float
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Greedy highest-score-first assignment.

    Greedy rather than Hungarian: on fixed-camera traffic footage the IoU
    matrix is near-diagonal because vehicles rarely swap positions between
    frames, so the optimal assignment and the greedy one almost always agree,
    and greedy avoids a scipy dependency in the inner loop.
    """
    matches: list[tuple[int, int]] = []
    used_rows: set[int] = set()
    used_columns: set[int] = set()

    if scores.size:
        order = np.dstack(np.unravel_index(np.argsort(-scores, axis=None), scores.shape))[0]
        for row, column in order:
            row, column = int(row), int(column)
            if row in used_rows or column in used_columns:
                continue
            if scores[row, column] < threshold:
                break
            matches.append((row, column))
            used_rows.add(row)
            used_columns.add(column)

    unmatched_rows = [index for index in range(scores.shape[0]) if index not in used_rows]
    unmatched_columns = [index for index in range(scores.shape[1]) if index not in used_columns]
    return matches, unmatched_rows, unmatched_columns


class ByteTracker:
    """IoU-association tracker with ByteTrack's two-stage matching."""

    #: Detections at or above this confidence are matched in the first pass.
    HIGH_CONFIDENCE = 0.5

    def __init__(self, config: TrackerConfig | None = None) -> None:
        self._config = config or TrackerConfig()
        self._states: list[_TrackState] = []
        self._next_id = 1
        self._info = TrackerInfo(name="bytetrack", version="1.0")

    @property
    def info(self) -> TrackerInfo:
        return self._info

    @property
    def config(self) -> TrackerConfig:
        return self._config

    def reset(self) -> None:
        """Clear all state. Track ids are per-video and must not leak across videos."""
        self._states = []
        self._next_id = 1

    def update(self, detections: list[Detection], meta: FrameMeta) -> list[Track]:
        for state in self._states:
            state.age += 1
            state.frames_since_update += 1
            # Advance the constant-velocity prediction.
            state.mean[0] += state.mean[4]
            state.mean[1] += state.mean[5]

        high = [d for d in detections if d.confidence >= self.HIGH_CONFIDENCE]
        low = [d for d in detections if d.confidence < self.HIGH_CONFIDENCE]

        # Pass 1: confident detections against all tracks.
        matches, unmatched_tracks, unmatched_high = _greedy_match(
            _iou_matrix(self._states, high), self._config.minimum_matching_threshold
        )
        for track_index, detection_index in matches:
            self._apply(self._states[track_index], high[detection_index], meta)

        # Pass 2: low-confidence detections rescue still-unmatched tracks. This
        # is what keeps an occluded vehicle's identity intact.
        remaining = [self._states[index] for index in unmatched_tracks]
        low_matches, _, _ = _greedy_match(
            _iou_matrix(remaining, low), self._config.second_pass_threshold
        )
        for track_index, detection_index in low_matches:
            self._apply(remaining[track_index], low[detection_index], meta)

        # New tracks from confident, unmatched detections only: starting a
        # track from a low-confidence box is how phantom vehicles appear.
        for detection_index in unmatched_high:
            detection = high[detection_index]
            if detection.confidence >= self._config.track_activation_threshold:
                self._start(detection, meta)

        # Drop tracks unmatched for longer than the buffer. An unconfirmed
        # track is dropped immediately on a miss: it was probably a false
        # positive, and keeping it risks re-matching it to a different vehicle.
        self._states = [
            state
            for state in self._states
            if state.frames_since_update
            <= (self._config.lost_track_buffer_frames if state.confirmed else 0)
        ]

        return [
            state.track
            for state in self._states
            if state.confirmed and state.frames_since_update == 0
        ]

    def finalize(self) -> list[Track]:
        """All tracks that were ever confirmed, including those still in the buffer."""
        return [state.track for state in self._states if state.confirmed]

    # ---------------------------------------------------------------- internal

    def _start(self, detection: Detection, meta: FrameMeta) -> None:
        track = Track(track_id=self._next_id, vehicle_class=detection.vehicle_class)
        self._next_id += 1

        state = _TrackState(track=track, mean=_to_state(detection.box))
        point = TrackPoint(
            frame_index=meta.index,
            timestamp_s=meta.timestamp_s,
            box=detection.box,
            confidence=detection.confidence,
        )

        if self._config.minimum_consecutive_frames <= 1:
            state.confirmed = True
            track.add_point(point, detection.vehicle_class)
        else:
            # Held back until confirmed, then flushed, so a single-frame false
            # positive never reaches the event stream at all.
            state.pending_points.append(point)

        self._states.append(state)

    def _apply(self, state: _TrackState, detection: Detection, meta: FrameMeta) -> None:
        previous = state.mean.copy()
        centre = detection.box.center

        # Velocity from the observed displacement, lightly smoothed so a single
        # noisy box does not throw the prediction.
        state.mean[4] = 0.7 * previous[4] + 0.3 * (centre.x - previous[0])
        state.mean[5] = 0.7 * previous[5] + 0.3 * (centre.y - previous[1])
        state.mean[0] = centre.x
        state.mean[1] = centre.y
        state.mean[2] = detection.box.width
        state.mean[3] = detection.box.height

        state.hits += 1
        state.frames_since_update = 0

        point = TrackPoint(
            frame_index=meta.index,
            timestamp_s=meta.timestamp_s,
            box=detection.box,
            confidence=detection.confidence,
        )

        if state.confirmed:
            state.track.add_point(point, detection.vehicle_class)
            return

        state.pending_points.append(point)
        if state.hits >= self._config.minimum_consecutive_frames:
            state.confirmed = True
            for pending in state.pending_points:
                state.track.add_point(pending, detection.vehicle_class)
            state.pending_points.clear()


def tracker_for(frame_rate: float, stride: int = 1) -> ByteTracker:
    """Build a tracker with buffers scaled to the effective frame rate.

    The lost-track buffer is expressed in frames, so a 15 fps camera sampled
    every second frame needs a very different value from 60 fps sampled every
    frame. Getting this wrong either drops identities mid-occlusion or keeps
    dead tracks alive long enough to be re-matched to a different vehicle.
    """
    effective = max(1.0, frame_rate / max(1, stride))
    return ByteTracker(
        TrackerConfig(
            frame_rate=effective,
            lost_track_buffer_frames=max(5, int(effective)),
            minimum_consecutive_frames=2 if effective < 15 else 3,
        )
    )


__all__ = ["ByteTracker", "tracker_for", "VehicleClass"]
