"""Tracking, motion, safety detection and conflict analysis.

These use the scripted detector, which replays a known scenario, so a failure
here is unambiguous: the ground truth is what the script says it is.
"""

from __future__ import annotations

import pytest

from trajyx_cv.detection.scripted import ScriptedActor, ScriptedDetector
from trajyx_cv.interactions.conflict import analyse_pair, find_near_misses
from trajyx_cv.trajectory.motion import (
    MAX_PLAUSIBLE_ACCELERATION_MS2,
    Calibration,
    analyse,
    apply_to_track,
    dominant_heading,
    representative_width,
)
from trajyx_cv.tracking.base import TrackerConfig
from trajyx_cv.tracking.bytetrack import ByteTracker, tracker_for
from trajyx_cv.types import BoundingBox, Detection, FrameMeta, Track, TrackPoint
from trajyx_cv.violations.detectors import (
    Availability,
    CameraContext,
    LaneDirection,
    StopLineGeometry,
    detect_hard_braking,
    detect_helmet,
    detect_red_light_violation,
    detect_stop_line_violation,
    detect_wrong_way,
    determination_for,
)
from trajyx_shared.domain import Determination, EventType, SignalState, VehicleClass

FRAME_RATE = 25.0
CALIBRATION = Calibration(metres_per_pixel_at_reference=0.09, reference_y=430, frame_height=540)


def run_detector(detector: ScriptedDetector, frames: int = 100, stride: int = 1) -> list[Track]:
    """Feed a scripted detector through the tracker and return finished tracks."""
    tracker = tracker_for(FRAME_RATE, stride)
    for index in range(0, frames, stride):
        meta = FrameMeta(index=index, timestamp_s=index / FRAME_RATE, width=960, height=540)
        tracker.update(detector.detect(None, meta), meta)  # type: ignore[arg-type]
    return tracker.finalize()


def make_track(points: list[tuple[float, float]], vehicle_class=VehicleClass.CAR) -> Track:
    track = Track(track_id=1, vehicle_class=vehicle_class)
    for index, (x, y) in enumerate(points):
        track.add_point(
            TrackPoint(
                frame_index=index,
                timestamp_s=index / FRAME_RATE,
                box=BoundingBox(x, y, x + 70, y + 34),
                confidence=0.9,
            ),
            vehicle_class,
        )
    return track


class TestTracking:
    def test_a_moving_vehicle_keeps_one_identity(self) -> None:
        detector = ScriptedDetector(
            actors=[ScriptedActor(VehicleClass.CAR, 100, 300, velocity_x=110)], jitter_px=0.0
        )
        tracks = run_detector(detector, frames=60)

        assert len(tracks) == 1
        assert tracks[0].vehicle_class is VehicleClass.CAR
        assert len(tracks[0].points) >= 55

    def test_identity_survives_a_low_confidence_occlusion(self) -> None:
        """ByteTrack's second association pass exists for exactly this.

        Without it, a partially occluded vehicle becomes two tracks, and the
        trajectory that wrong-way and near-miss detection depend on is lost.
        """
        detector = ScriptedDetector(
            actors=[
                ScriptedActor(
                    VehicleClass.CAR, 100, 300, velocity_x=110, occluded_between_s=(1.0, 1.8)
                )
            ],
            jitter_px=0.0,
        )
        tracks = run_detector(detector, frames=80)
        assert len(tracks) == 1

    def test_two_vehicles_stay_distinct(self) -> None:
        detector = ScriptedDetector(
            actors=[
                ScriptedActor(VehicleClass.CAR, 100, 260, velocity_x=110),
                ScriptedActor(VehicleClass.TRUCK, 800, 440, velocity_x=-95, width=100, height=46),
            ],
            jitter_px=0.0,
        )
        tracks = run_detector(detector, frames=60)

        assert len(tracks) == 2
        assert {track.vehicle_class for track in tracks} == {VehicleClass.CAR, VehicleClass.TRUCK}
        assert len({track.track_id for track in tracks}) == 2

    def test_a_single_frame_detection_never_becomes_a_track(self) -> None:
        """Otherwise one false positive becomes a phantom vehicle in the counts."""
        tracker = ByteTracker(TrackerConfig(minimum_consecutive_frames=3))
        meta = FrameMeta(index=0, timestamp_s=0.0, width=960, height=540)
        tracker.update(
            [Detection(VehicleClass.CAR, 0.9, BoundingBox(10, 10, 80, 44), 0, 0.0)], meta
        )
        for index in range(1, 8):
            tracker.update([], FrameMeta(index, index / FRAME_RATE, 960, 540))

        assert tracker.finalize() == []

    def test_reset_clears_identities_between_videos(self) -> None:
        """Track ids are per-video; leaking them would correlate vehicles across
        unrelated footage, which the privacy design forbids."""
        tracker = ByteTracker(TrackerConfig(minimum_consecutive_frames=1))
        meta = FrameMeta(0, 0.0, 960, 540)
        tracker.update([Detection(VehicleClass.CAR, 0.9, BoundingBox(0, 0, 70, 34), 0, 0.0)], meta)
        first = tracker.finalize()[0].track_id

        tracker.reset()
        tracker.update([Detection(VehicleClass.CAR, 0.9, BoundingBox(0, 0, 70, 34), 0, 0.0)], meta)
        assert tracker.finalize()[0].track_id == first == 1

    def test_iou_threshold_admits_realistic_motion(self) -> None:
        """Regression: the published ByteTrack 0.8 is a *cost* threshold on
        1 - IoU. Used as a raw IoU score it rejects any vehicle moving more
        than a few pixels per frame, so nothing was ever tracked."""
        config = TrackerConfig()
        assert config.minimum_matching_threshold <= 0.3


class TestMotion:
    def test_speed_is_none_without_calibration(self) -> None:
        """A pixel figure presented as km/h is the easiest lie to tell."""
        track = make_track([(100 + index * 20, 300) for index in range(12)])
        samples = analyse(track, calibration=None)

        assert samples
        assert all(sample.speed_kmh is None for sample in samples)
        assert all(sample.acceleration_kmh_s is None for sample in samples)
        # Pixel speed is still available for geometry that does not need metres.
        assert any(sample.speed_px_per_s > 0 for sample in samples)

    def test_speed_is_estimated_with_calibration(self) -> None:
        track = make_track([(100 + index * 20, 430) for index in range(12)])
        samples = analyse(track, CALIBRATION)

        speeds = [s.speed_kmh for s in samples if s.speed_kmh is not None]
        assert speeds
        # 20 px/frame at 25 fps = 500 px/s; x0.09 m/px = 45 m/s = 162 km/h.
        assert 100 < max(speeds) < 200

    def test_implausible_acceleration_is_discarded_as_noise(self) -> None:
        """Regression: differentiating jittery positions produced 34 m/s^2 —
        3.5 g — and turned that into 52 phantom hard-braking events."""
        track = make_track([(100 + index * 20, 430) for index in range(20)])
        samples = analyse(track, CALIBRATION)

        for sample in samples:
            if sample.acceleration_kmh_s is not None:
                assert abs(sample.acceleration_kmh_s / 3.6) <= MAX_PLAUSIBLE_ACCELERATION_MS2

    def test_heading_is_none_when_the_vehicle_has_not_moved(self) -> None:
        """A jittered heading on a stationary vehicle would fire wrong-way."""
        track = make_track([(100, 300)] * 12)
        samples = analyse(track, CALIBRATION)
        assert all(sample.heading_deg is None for sample in samples)

    @pytest.mark.parametrize(
        ("delta", "expected"),
        [((20, 0), 90.0), ((-20, 0), 270.0), ((0, -20), 0.0), ((0, 20), 180.0)],
    )
    def test_heading_matches_compass_convention(
        self, delta: tuple[float, float], expected: float
    ) -> None:
        dx, dy = delta
        track = make_track([(300 + index * dx, 300 + index * dy) for index in range(14)])
        heading = dominant_heading(analyse(track, CALIBRATION))
        assert heading is not None
        assert abs(heading - expected) < 5.0 or abs(heading - expected) > 355.0

    def test_representative_width_ignores_clipped_boxes(self) -> None:
        """Regression: the per-frame width of a vehicle entering frame is
        clipped, which made a 70px car measure 11px and turned ordinary travel
        into a 'dangerous lane change'."""
        track = Track(track_id=1, vehicle_class=VehicleClass.CAR)
        for index, box in enumerate(
            [
                BoundingBox(0, 300, 8, 334),  # clipped at the frame edge
                BoundingBox(0, 300, 70, 334),
                BoundingBox(20, 300, 90, 334),
                BoundingBox(40, 300, 110, 334),
            ]
        ):
            track.add_point(TrackPoint(index, index / FRAME_RATE, box, 0.9), VehicleClass.CAR)

        assert representative_width(track) >= 60

    def test_apply_writes_results_back_onto_the_track(self) -> None:
        track = make_track([(100 + index * 20, 430) for index in range(12)])
        apply_to_track(track, CALIBRATION)
        assert any(point.speed_kmh is not None for point in track.points)
        assert any(point.heading_deg is not None for point in track.points)


class TestWrongWay:
    EASTBOUND = LaneDirection(0, 90.0, region_y_min=225, region_y_max=340)
    WESTBOUND = LaneDirection(1, 270.0, region_y_min=395, region_y_max=500)

    def context(self, *lanes: LaneDirection) -> CameraContext:
        return CameraContext(calibration=CALIBRATION, lane_directions=lanes)

    def test_a_vehicle_going_the_right_way_is_not_flagged(self) -> None:
        track = make_track([(100 + index * 22, 260) for index in range(40)])
        result = detect_wrong_way(
            track, analyse(track, CALIBRATION), self.context(self.EASTBOUND, self.WESTBOUND)
        )
        assert result.availability is Availability.AVAILABLE
        assert result.findings == ()

    def test_a_vehicle_opposing_its_own_lane_is_flagged(self) -> None:
        """The headline case: eastbound travel in the westbound lane.

        Regression: comparing the heading against the *closest* configured
        heading matched this vehicle to the eastbound lane and declared it
        fine. The lane has to be chosen by position.
        """
        track = make_track([(100 + index * 22, 450) for index in range(40)])
        result = detect_wrong_way(
            track, analyse(track, CALIBRATION), self.context(self.EASTBOUND, self.WESTBOUND)
        )

        assert result.availability is Availability.AVAILABLE
        assert len(result.findings) == 1

        finding = result.findings[0]
        assert finding.event_type is EventType.WRONG_WAY
        assert finding.details["lane_index"] == 1
        assert finding.details["angular_difference_deg"] > 170
        assert finding.confidence > 0.9

    def test_unavailable_without_any_lane_configuration(self) -> None:
        track = make_track([(100 + index * 22, 450) for index in range(40)])
        result = detect_wrong_way(track, analyse(track, CALIBRATION), self.context())
        assert result.availability is Availability.UNAVAILABLE
        assert "No lane direction configured" in (result.unavailable_reason or "")

    def test_unavailable_when_lanes_have_headings_but_no_regions(self) -> None:
        """A heading alone cannot say which lane a vehicle is in, so the check
        reports that rather than guessing."""
        track = make_track([(100 + index * 22, 450) for index in range(40)])
        result = detect_wrong_way(
            track,
            analyse(track, CALIBRATION),
            self.context(LaneDirection(0, 90.0), LaneDirection(1, 270.0)),
        )
        assert result.availability is Availability.UNAVAILABLE
        assert "lane regions" in (result.unavailable_reason or "")

    def test_a_brief_track_is_not_flagged(self) -> None:
        """One second of opposing heading is noise, not a wrong-way vehicle."""
        track = make_track([(100 + index * 22, 450) for index in range(10)])
        result = detect_wrong_way(
            track, analyse(track, CALIBRATION), self.context(self.EASTBOUND, self.WESTBOUND)
        )
        assert result.findings == ()


class TestGatedDetectors:
    def test_hard_braking_is_unavailable_without_calibration(self) -> None:
        track = make_track([(100 + index * 20, 300) for index in range(20)])
        result = detect_hard_braking(track, analyse(track, None), CameraContext())

        assert result.availability is Availability.UNAVAILABLE
        assert "not calibrated" in (result.unavailable_reason or "")
        # The point of the tri-state: this is not "no braking occurred".
        assert determination_for(result) is Determination.UNABLE_TO_DETERMINE

    def test_hard_braking_fires_on_a_real_deceleration(self) -> None:
        # A physically realistic brake, around 6 m/s^2 (0.6 g).
        #
        # At the reference row the scale is 0.09 m/px, so v px/frame at 25 fps
        # is 2.25v m/s. Losing 0.107 px/frame each frame is therefore about
        # 6 m/s^2 — hard, but well inside what a car can actually do. An
        # earlier version of this test decelerated at 225 m/s^2, which the
        # plausibility gate correctly threw away as tracking noise.
        positions = []
        x = 100.0
        step = 8.0
        for _ in range(40):
            positions.append((x, 430.0))
            x += step
            step = max(1.0, step - 0.107)

        track = make_track(positions)
        result = detect_hard_braking(track, analyse(track, CALIBRATION), CameraContext(calibration=CALIBRATION))

        assert result.availability is Availability.AVAILABLE
        assert result.findings
        assert result.findings[0].event_type is EventType.HARD_BRAKING

    def test_red_light_is_unavailable_when_the_phase_is_unknown(self) -> None:
        """The most consequential refusal in the system: a red-light violation
        must never be inferred without knowing the signal was red."""
        track = make_track([(600 + index * 20, 300) for index in range(20)])
        context = CameraContext(
            calibration=CALIBRATION,
            stop_line=StopLineGeometry(start=make_point(700, 200), end=make_point(700, 520)),
            signal_state=SignalState.UNKNOWN,
        )
        result = detect_red_light_violation(track, analyse(track, CALIBRATION), context)

        assert result.availability is Availability.UNAVAILABLE
        assert "Signal phase is unknown" in (result.unavailable_reason or "")

    def test_red_light_fires_when_the_phase_is_red(self) -> None:
        track = make_track([(600 + index * 20, 300) for index in range(20)])
        context = CameraContext(
            calibration=CALIBRATION,
            stop_line=StopLineGeometry(start=make_point(700, 200), end=make_point(700, 520)),
            signal_state=SignalState.RED,
        )
        result = detect_red_light_violation(track, analyse(track, CALIBRATION), context)

        assert result.availability is Availability.AVAILABLE
        assert result.findings
        assert result.findings[0].event_type is EventType.RED_LIGHT_VIOLATION

    def test_no_red_light_violation_on_green(self) -> None:
        track = make_track([(600 + index * 20, 300) for index in range(20)])
        context = CameraContext(
            calibration=CALIBRATION,
            stop_line=StopLineGeometry(start=make_point(700, 200), end=make_point(700, 520)),
            signal_state=SignalState.GREEN,
        )
        result = detect_red_light_violation(track, analyse(track, CALIBRATION), context)
        assert result.availability is Availability.AVAILABLE
        assert result.findings == ()

    def test_stop_line_crossing_is_detected(self) -> None:
        track = make_track([(600 + index * 20, 300) for index in range(20)])
        context = CameraContext(
            calibration=CALIBRATION,
            stop_line=StopLineGeometry(start=make_point(700, 200), end=make_point(700, 520)),
        )
        result = detect_stop_line_violation(track, analyse(track, CALIBRATION), context)
        assert result.findings

    def test_helmet_detection_refuses_rather_than_guessing(self) -> None:
        """A helmet determination inferred from a vehicle box would be a
        fabricated claim about a real person's compliance."""
        track = make_track([(100 + index * 20, 300) for index in range(20)], VehicleClass.MOTORCYCLE)
        result = detect_helmet(track, analyse(track, CALIBRATION), CameraContext())

        assert result.availability is Availability.UNAVAILABLE
        assert determination_for(result) is Determination.UNABLE_TO_DETERMINE

    def test_helmet_check_does_not_apply_to_cars(self) -> None:
        track = make_track([(100 + index * 20, 300) for index in range(20)], VehicleClass.CAR)
        result = detect_helmet(track, analyse(track, CALIBRATION), CameraContext())
        assert result.availability is Availability.AVAILABLE
        assert result.findings == ()


class TestConflicts:
    def test_a_closing_pair_produces_a_short_ttc(self) -> None:
        leader = make_track([(400 + index * 6, 300) for index in range(30)])
        follower = Track(track_id=2, vehicle_class=VehicleClass.CAR)
        for index in range(30):
            x = 100 + index * 18
            follower.add_point(
                TrackPoint(index, index / FRAME_RATE, BoundingBox(x, 302, x + 70, 336), 0.9),
                VehicleClass.CAR,
            )

        interactions = analyse_pair(
            leader, follower, analyse(leader, CALIBRATION), analyse(follower, CALIBRATION), CALIBRATION
        )
        assert interactions

        ttcs = [i.estimated_ttc_s for i in interactions if i.estimated_ttc_s is not None]
        assert ttcs
        assert min(ttcs) < 5.0
        assert all(i.gap_m is not None for i in interactions)

    def test_parallel_traffic_in_separate_lanes_is_not_a_near_miss(self) -> None:
        """Regression: gap-based closing speed on jittery boxes turned two
        vehicles travelling side by side into a stream of near misses."""
        first = make_track([(100 + index * 20, 250) for index in range(40)])
        second = Track(track_id=2, vehicle_class=VehicleClass.CAR)
        for index in range(40):
            x = 100 + index * 20
            second.add_point(
                TrackPoint(index, index / FRAME_RATE, BoundingBox(x, 440, x + 70, 474), 0.9),
                VehicleClass.CAR,
            )

        interactions = analyse_pair(
            first, second, analyse(first, CALIBRATION), analyse(second, CALIBRATION), CALIBRATION
        )
        assert find_near_misses(interactions) == []

    def test_a_single_noisy_frame_is_not_a_near_miss(self) -> None:
        from trajyx_cv.interactions.conflict import Interaction

        one = [
            Interaction(
                frame_index=5,
                timestamp_s=0.2,
                track_a=1,
                track_b=2,
                class_a=VehicleClass.CAR,
                class_b=VehicleClass.CAR,
                gap_px=4.0,
                closing_speed_px_s=200.0,
                estimated_ttc_s=0.02,
                ttc_band=None,
                paths_converge=True,
                relative_speed_px_s=50.0,
                interaction_score=90.0,
            )
        ]
        assert find_near_misses(one) == []

    def test_near_miss_carries_human_readable_factors(self) -> None:
        """An unexplained risk score is not actionable; the factors are the
        explanation shown to operators and drivers."""
        leader = make_track([(400 + index * 4, 300) for index in range(30)])
        follower = Track(track_id=2, vehicle_class=VehicleClass.MOTORCYCLE)
        for index in range(30):
            x = 120 + index * 20
            follower.add_point(
                TrackPoint(index, index / FRAME_RATE, BoundingBox(x, 302, x + 40, 332), 0.9),
                VehicleClass.MOTORCYCLE,
            )

        interactions = analyse_pair(
            leader, follower, analyse(leader, CALIBRATION), analyse(follower, CALIBRATION), CALIBRATION
        )
        near_misses = find_near_misses(interactions)

        assert near_misses
        assert near_misses[0].risk_factors
        assert any("Vulnerable road user" in factor for factor in near_misses[0].risk_factors)

    def test_tracks_that_never_overlap_produce_nothing(self) -> None:
        first = make_track([(100 + index * 20, 300) for index in range(10)])
        second = Track(track_id=2, vehicle_class=VehicleClass.CAR)
        for index in range(50, 60):
            x = 100 + index * 20
            second.add_point(
                TrackPoint(index, index / FRAME_RATE, BoundingBox(x, 300, x + 70, 334), 0.9),
                VehicleClass.CAR,
            )

        assert analyse_pair(first, second, analyse(first), analyse(second)) == []


def make_point(x: float, y: float):
    from trajyx_cv.types import Point

    return Point(x, y)
