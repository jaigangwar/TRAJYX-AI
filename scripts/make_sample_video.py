"""Render a synthetic traffic clip for pipeline verification.

Draws a road with vehicles that YOLO can actually detect (simple but
car-shaped), including one deliberately wrong-way vehicle and one converging
pair, so the safety and conflict detectors have something real to find.

This is a *test fixture*, not demo data: it exists so the pipeline can be
verified without shipping copyrighted CCTV footage, and anything analysed from
it is labelled accordingly.

    python scripts/make_sample_video.py datasets/samples/junction.mp4
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

WIDTH, HEIGHT = 960, 540
FPS = 25
SECONDS = 12


def draw_road(canvas: np.ndarray) -> None:
    # Asphalt
    cv2.rectangle(canvas, (0, 180), (WIDTH, HEIGHT), (58, 58, 60), -1)
    # Verges
    cv2.rectangle(canvas, (0, 0), (WIDTH, 180), (70, 85, 72), -1)
    # Lane markings
    for x in range(0, WIDTH, 60):
        cv2.rectangle(canvas, (x, 355), (x + 34, 361), (225, 225, 225), -1)
    cv2.line(canvas, (0, 190), (WIDTH, 190), (225, 225, 225), 2)
    cv2.line(canvas, (0, HEIGHT - 10), (WIDTH, HEIGHT - 10), (225, 225, 225), 2)


def draw_car(canvas: np.ndarray, x: float, y: float, scale: float, colour: tuple[int, int, int]) -> None:
    """A crude but recognisable car silhouette."""
    w = int(76 * scale)
    h = int(34 * scale)
    x, y = int(x), int(y)

    # Body
    cv2.rectangle(canvas, (x, y), (x + w, y + h), colour, -1)
    # Cabin
    cv2.rectangle(
        canvas,
        (x + int(w * 0.22), y - int(h * 0.45)),
        (x + int(w * 0.74), y + 2),
        tuple(int(c * 0.8) for c in colour),
        -1,
    )
    # Windscreen
    cv2.rectangle(
        canvas,
        (x + int(w * 0.28), y - int(h * 0.38)),
        (x + int(w * 0.68), y - int(h * 0.05)),
        (110, 130, 140),
        -1,
    )
    # Wheels
    radius = max(3, int(h * 0.28))
    cv2.circle(canvas, (x + int(w * 0.22), y + h), radius, (25, 25, 25), -1)
    cv2.circle(canvas, (x + int(w * 0.78), y + h), radius, (25, 25, 25), -1)


def draw_person(canvas: np.ndarray, x: float, y: float, scale: float) -> None:
    x, y = int(x), int(y)
    h = int(46 * scale)
    cv2.circle(canvas, (x, y - h), max(3, int(7 * scale)), (196, 174, 150), -1)
    cv2.rectangle(
        canvas,
        (x - int(7 * scale), y - h + int(8 * scale)),
        (x + int(7 * scale), y - int(h * 0.35)),
        (60, 80, 170),
        -1,
    )
    cv2.line(canvas, (x - int(4 * scale), y - int(h * 0.35)), (x - int(5 * scale), y), (45, 45, 70), max(2, int(3 * scale)))
    cv2.line(canvas, (x + int(4 * scale), y - int(h * 0.35)), (x + int(5 * scale), y), (45, 45, 70), max(2, int(3 * scale)))


def render(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT)
    )
    if not writer.isOpened():
        raise RuntimeError(f"Cannot open writer for {output}")

    total = FPS * SECONDS
    try:
        for frame_index in range(total):
            t = frame_index / FPS
            canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
            draw_road(canvas)

            # Eastbound lane (upper), normal direction.
            draw_car(canvas, -100 + 95 * t, 250, 1.0, (170, 165, 60))
            draw_car(canvas, -320 + 78 * t, 255, 1.05, (70, 90, 185))

            # Westbound lane (lower), normal direction.
            draw_car(canvas, WIDTH + 60 - 88 * t, 430, 1.25, (60, 150, 90))

            # WRONG WAY: travelling east in the westbound lane.
            draw_car(canvas, -200 + 105 * t, 455, 1.25, (55, 60, 200))

            # A converging pair around t=6s: one slows hard, the follower closes.
            leader_x = 120 + 70 * t - (28 * max(0.0, t - 5.5) ** 2 if t > 5.5 else 0.0)
            follower_x = leader_x - max(30.0, 210 - 26 * t)
            draw_car(canvas, leader_x, 300, 1.1, (200, 180, 90))
            draw_car(canvas, follower_x, 305, 1.1, (150, 70, 170))

            # Pedestrian crossing in the second half.
            if t > 6.0:
                draw_person(canvas, 520, 210 + 34 * (t - 6.0), 1.0)

            # Mild sensor noise so the frames are not unnaturally clean.
            noise = np.random.default_rng(frame_index).integers(-5, 6, canvas.shape, dtype=np.int16)
            canvas = np.clip(canvas.astype(np.int16) + noise, 0, 255).astype(np.uint8)

            writer.write(canvas)
    finally:
        writer.release()

    print(f"wrote {output}  {WIDTH}x{HEIGHT}  {FPS}fps  {SECONDS}s  ({total} frames)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", default="datasets/samples/junction.mp4")
    args = parser.parse_args()
    render(Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
