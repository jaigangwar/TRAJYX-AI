"""Video decoding and frame sampling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

from trajyx_cv.types import FrameMeta


@dataclass(frozen=True, slots=True)
class VideoInfo:
    path: Path
    width: int
    height: int
    frame_rate: float
    frame_count: int

    @property
    def duration_s(self) -> float:
        return self.frame_count / self.frame_rate if self.frame_rate > 0 else 0.0


class VideoReadError(RuntimeError):
    pass


def probe(path: Path) -> VideoInfo:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise VideoReadError(f"Cannot open video: {path}")
    try:
        frame_rate = float(capture.get(cv2.CAP_PROP_FPS)) or 25.0
        return VideoInfo(
            path=path,
            width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            # A container can report a nonsense rate; 25 is a safe fallback and
            # only affects timestamps, not detection.
            frame_rate=frame_rate if 1.0 <= frame_rate <= 240.0 else 25.0,
            frame_count=int(capture.get(cv2.CAP_PROP_FRAME_COUNT)),
        )
    finally:
        capture.release()


def read_frames(
    path: Path, stride: int = 1, max_frames: int | None = None
) -> Iterator[tuple[np.ndarray, FrameMeta]]:
    """Yield (BGR frame, meta) pairs, sampling every `stride`-th frame.

    `meta.index` is the index in the *source* video, not the sampled sequence,
    so an event can always be traced back to a real frame for evidence.
    Timestamps come from the frame rate rather than CAP_PROP_POS_MSEC, which is
    unreliable across containers.
    """
    if stride < 1:
        raise ValueError("stride must be >= 1")

    info = probe(path)
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise VideoReadError(f"Cannot open video: {path}")

    try:
        source_index = 0
        emitted = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break

            if source_index % stride == 0:
                yield (
                    frame,
                    FrameMeta(
                        index=source_index,
                        timestamp_s=source_index / info.frame_rate,
                        width=info.width,
                        height=info.height,
                    ),
                )
                emitted += 1
                if max_frames is not None and emitted >= max_frames:
                    break
            source_index += 1
    finally:
        capture.release()


class AnnotatedWriter:
    """Writes the annotated output video."""

    def __init__(self, path: Path, width: int, height: int, frame_rate: float) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # mp4v rather than H.264: it is available in every OpenCV build,
        # whereas avc1 depends on system codecs being present.
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(str(path), fourcc, max(1.0, frame_rate), (width, height))
        if not self._writer.isOpened():
            raise VideoReadError(f"Cannot open video writer for {path}")
        self.path = path

    def write(self, frame: np.ndarray) -> None:
        self._writer.write(frame)

    def close(self) -> None:
        self._writer.release()

    def __enter__(self) -> AnnotatedWriter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
