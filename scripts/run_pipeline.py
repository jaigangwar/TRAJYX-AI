"""Run the analysis pipeline over a video and print what it found.

    python scripts/run_pipeline.py datasets/samples/junction.mp4
    python scripts/run_pipeline.py <video> --detector yolo
    python scripts/run_pipeline.py <video> --annotate .verify/annotated.mp4

`--detector scripted` replays a known scenario, which is how the tracking,
motion, safety and conflict stages are verified against a ground truth.
`--detector yolo` runs real detection.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def build_context(frame_height: int, *, calibrated: bool, lanes: bool, stop_line: bool):
    from trajyx_cv.trajectory.motion import Calibration
    from trajyx_cv.types import Point
    from trajyx_cv.violations.detectors import CameraContext, LaneDirection, StopLineGeometry

    return CameraContext(
        calibration=(
            Calibration(
                metres_per_pixel_at_reference=0.09,
                reference_y=frame_height * 0.8,
                frame_height=frame_height,
            )
            if calibrated
            else None
        ),
        lane_directions=(
            (
                LaneDirection(0, 90.0, region_y_min=225, region_y_max=340),
                LaneDirection(1, 270.0, region_y_min=395, region_y_max=500),
            )
            if lanes
            else ()
        ),
        stop_line=(
            StopLineGeometry(start=Point(700, 200), end=Point(700, 520)) if stop_line else None
        ),
        speed_limit_kmh=50.0,
        frame_height=frame_height,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the TRAJYX analysis pipeline.")
    parser.add_argument("video")
    parser.add_argument("--detector", choices=["scripted", "yolo"], default="scripted")
    parser.add_argument("--weights", default="yolov8n.pt")
    parser.add_argument("--stride", type=int, default=2)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--annotate", default=None)
    parser.add_argument("--no-calibration", action="store_true")
    parser.add_argument("--no-lanes", action="store_true")
    parser.add_argument("--stop-line", action="store_true")
    args = parser.parse_args()

    from trajyx_cv.pipeline import analyse_video
    from trajyx_cv.video.reader import probe

    video = Path(args.video)
    info = probe(video)
    print(
        f"video: {video}  {info.width}x{info.height}  {info.frame_rate:.1f}fps  "
        f"{info.frame_count} frames  {info.duration_s:.1f}s\n"
    )

    if args.detector == "yolo":
        from trajyx_cv.detection.yolo import YoloDetector

        detector = YoloDetector(args.weights, confidence=0.25, device="cpu")
    else:
        from trajyx_cv.detection.scripted import junction_scenario

        detector = junction_scenario()

    context = build_context(
        info.height,
        calibrated=not args.no_calibration,
        lanes=not args.no_lanes,
        stop_line=args.stop_line,
    )

    result = analyse_video(
        video,
        detector,
        context=context,
        stride=args.stride,
        max_frames=args.max_frames,
        annotated_output=Path(args.annotate) if args.annotate else None,
    )

    print(f"detector        : {result.detector_name} {result.detector_version}")
    print(f"tracker         : {result.tracker_name}")
    print(f"frames analysed : {result.frames_processed} (stride {result.frame_stride})")
    print(f"detections      : {result.detection_count}")
    print(f"inference/frame : {result.inference_ms_per_frame} ms")
    print(f"wall time       : {result.wall_seconds} s")
    print()
    print(f"tracked vehicles: {result.vehicle_count}")
    print(f"pedestrians     : {result.pedestrian_count}")
    counts = {k.value: v for k, v in sorted(result.class_counts.items(), key=lambda x: -x[1])}
    print(f"class counts    : {counts}")
    if result.unmapped_labels:
        print(f"unmapped labels : {result.unmapped_labels}")
    print()

    print("tracks:")
    for track in result.tracks:
        samples = result.motion[track.track_id]
        speeds = [s.speed_kmh for s in samples if s.speed_kmh is not None]
        headings = [s.heading_deg for s in samples if s.heading_deg is not None]
        accels = [
            abs(s.acceleration_kmh_s) / 3.6 for s in samples if s.acceleration_kmh_s is not None
        ]
        print(
            f"  #{track.track_id:<3} {track.vehicle_class.value:<11} "
            f"points={len(track.points):<4} "
            f"speed~{(sum(speeds) / len(speeds) if speeds else 0):5.1f}km/h  "
            f"heading~{(sum(headings) / len(headings) if headings else -1):6.1f}deg  "
            f"peak|accel|={max(accels, default=0):5.2f}m/s2"
        )
    print()

    print(f"findings: {dict(Counter(f.event_type.value for f in result.findings))}")
    for finding in sorted(result.findings, key=lambda f: f.timestamp_s):
        print(
            f"  t={finding.timestamp_s:6.2f}s  #{finding.track_id:<3} "
            f"{finding.event_type.value:<22} conf={finding.confidence:.2f}  {finding.details}"
        )
    print()

    print(
        f"near misses: {len(result.near_misses)}   min estimated TTC: {result.minimum_ttc_s}s   "
        f"mean interaction: {result.mean_interaction_score}"
    )
    for near_miss in sorted(result.near_misses, key=lambda n: -n.interaction_score)[:6]:
        print(
            f"  t={near_miss.timestamp_s:6.2f}s tracks={near_miss.track_ids} "
            f"ttc={near_miss.estimated_ttc_s}s gap={near_miss.gap_m}m "
            f"score={near_miss.interaction_score} {near_miss.severity.value}"
        )
        for factor in near_miss.risk_factors:
            print(f"        - {factor}")
    print()

    print("checks that could not run:")
    for name, reason in sorted(result.unavailable_checks.items()):
        print(f"  {name:<22} {reason}")
    print()

    from app.risk.engine import RiskInputs, assess

    findings = Counter(f.event_type.value for f in result.findings)
    assessment = assess(
        RiskInputs(
            near_miss_count=len(result.near_misses),
            violation_count=(
                findings["WRONG_WAY"] + findings["OVERSPEED"] + findings["STOP_LINE_VIOLATION"]
            ),
            wrong_way_count=findings["WRONG_WAY"],
            hard_braking_count=findings["HARD_BRAKING"],
            sudden_acceleration_count=findings["SUDDEN_ACCELERATION"],
            lane_change_count=findings["DANGEROUS_LANE_CHANGE"],
            vehicle_count=result.vehicle_count,
            pedestrian_count=result.pedestrian_count,
            observation_hours=max(0.01, info.duration_s / 3600.0),
            minimum_ttc_s=result.minimum_ttc_s,
            mean_interaction_score=result.mean_interaction_score,
        )
    )
    print(
        f"RISK: {assessment.score}/100  {assessment.level.value}  "
        f"(confidence {assessment.confidence})"
    )
    for line in assessment.explain():
        print(f"  - {line}")

    if result.annotated_path:
        print(f"\nannotated video: {result.annotated_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
