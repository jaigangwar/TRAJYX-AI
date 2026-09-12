"""Geometry and track primitives.

These are the foundation every later stage computes on: a sign error in a
bearing or a wrong reference point in a box silently corrupts wrong-way
detection, speed estimation and near-miss scoring. They are tested directly.
"""

from __future__ import annotations

import math

import pytest

from trajyx_cv.detection.base import COCO_TO_VEHICLE_CLASS, map_detector_class
from trajyx_cv.types import (
    BoundingBox,
    Detection,
    Point,
    Track,
    TrackPoint,
    angular_difference,
    average_bearing,
    bearing_degrees,
)
from trajyx_shared.domain import Determination, VehicleClass


def box(x1: float, y1: float, x2: float, y2: float) -> BoundingBox:
    return BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)


class TestBoundingBox:
    def test_rejects_inverted_coordinates(self) -> None:
        with pytest.raises(ValueError, match="Degenerate bounding box"):
            box(50, 10, 10, 60)

    def test_allows_zero_area_box(self) -> None:
        # A detector clipped to a frame edge can legitimately produce this.
        assert box(10, 10, 10, 10).area == 0.0

    def test_dimensions(self) -> None:
        subject = box(10, 20, 50, 80)
        assert subject.width == 40
        assert subject.height == 60
        assert subject.area == 2400

    def test_center_and_ground_contact_point_differ(self) -> None:
        subject = box(10, 20, 50, 80)
        assert subject.center == Point(30, 50)
        # The ground-contact point sits on the bottom edge, not the middle:
        # projecting the centre would place a vehicle metres off the road.
        assert subject.bottom_center == Point(30, 80)

    def test_iou_of_identical_boxes_is_one(self) -> None:
        subject = box(10, 10, 50, 50)
        assert subject.iou(subject) == pytest.approx(1.0)

    def test_iou_of_disjoint_boxes_is_zero(self) -> None:
        assert box(0, 0, 10, 10).iou(box(20, 20, 30, 30)) == 0.0

    def test_iou_of_edge_touching_boxes_is_zero(self) -> None:
        # Shared edge, no overlapping area.
        assert box(0, 0, 10, 10).iou(box(10, 0, 20, 10)) == 0.0

    def test_iou_partial_overlap(self) -> None:
        # Overlap 20x30 = 600; areas 2000 and 2000; union 3400.
        first = box(10, 10, 50, 60)
        second = box(30, 30, 70, 80)
        assert first.iou(second) == pytest.approx(600 / 3400)

    def test_iou_is_symmetric(self) -> None:
        first = box(10, 10, 50, 60)
        second = box(30, 30, 70, 80)
        assert first.iou(second) == pytest.approx(second.iou(first))

    def test_contains_is_half_open(self) -> None:
        subject = box(0, 0, 10, 10)
        assert subject.contains(Point(0, 0))
        assert subject.contains(Point(9.99, 9.99))
        # Exclusive upper bound keeps adjacent boxes from both claiming a pixel.
        assert not subject.contains(Point(10, 10))

    def test_clip_to_frame_bounds(self) -> None:
        clipped = box(-20, -5, 700, 500).clip_to(640, 480)
        assert clipped.as_xyxy() == (0.0, 0.0, 640.0, 480.0)

    def test_xywh_conversion(self) -> None:
        assert box(10, 20, 50, 80).as_xywh() == (10.0, 20.0, 40.0, 60.0)


class TestBearing:
    """Bearings are clockwise from image-up, matching compass convention."""

    @pytest.mark.parametrize(
        ("origin", "destination", "expected"),
        [
            ((0, 100), (0, 0), 0.0),  # up the frame  -> north
            ((0, 0), (100, 0), 90.0),  # right         -> east
            ((0, 0), (0, 100), 180.0),  # down the frame-> south
            ((100, 0), (0, 0), 270.0),  # left          -> west
            ((0, 100), (100, 0), 45.0),  # up-right      -> north-east
        ],
    )
    def test_cardinal_directions(
        self, origin: tuple[float, float], destination: tuple[float, float], expected: float
    ) -> None:
        result = bearing_degrees(Point(*origin), Point(*destination))
        assert result == pytest.approx(expected)

    def test_coincident_points_return_zero(self) -> None:
        assert bearing_degrees(Point(5, 5), Point(5, 5)) == 0.0

    def test_result_is_always_in_range(self) -> None:
        for angle in range(0, 360, 7):
            radians = math.radians(angle)
            destination = Point(math.sin(radians) * 50, -math.cos(radians) * 50)
            result = bearing_degrees(Point(0, 0), destination)
            assert 0.0 <= result < 360.0


class TestAngularDifference:
    def test_wraps_across_north(self) -> None:
        # The whole point: 350 and 10 degrees are 20 apart, not 340.
        assert angular_difference(350, 10) == pytest.approx(20.0)
        assert angular_difference(10, 350) == pytest.approx(20.0)

    def test_opposite_directions(self) -> None:
        # This is the wrong-way signature.
        assert angular_difference(0, 180) == pytest.approx(180.0)
        assert angular_difference(90, 270) == pytest.approx(180.0)

    def test_identical_directions(self) -> None:
        assert angular_difference(137, 137) == 0.0

    def test_never_exceeds_half_turn(self) -> None:
        for first in range(0, 360, 11):
            for second in range(0, 360, 13):
                assert 0.0 <= angular_difference(first, second) <= 180.0


class TestAverageBearing:
    def test_averages_across_the_wrap_point(self) -> None:
        # An arithmetic mean would give 180 here, which is the opposite heading.
        assert average_bearing([350, 10]) == pytest.approx(0.0, abs=1e-6)

    def test_simple_case(self) -> None:
        assert average_bearing([80, 100]) == pytest.approx(90.0)

    def test_empty_input_is_undefined(self) -> None:
        assert average_bearing([]) is None

    def test_cancelling_bearings_are_undefined(self) -> None:
        # Two exactly opposite headings have no meaningful mean; returning 0
        # (i.e. "north") would be a fabricated direction.
        assert average_bearing([0, 180]) is None


class TestDetection:
    def test_rejects_out_of_range_confidence(self) -> None:
        with pytest.raises(ValueError, match=r"confidence must be in \[0, 1\]"):
            Detection(
                vehicle_class=VehicleClass.CAR,
                confidence=1.4,
                box=box(0, 0, 10, 10),
                frame_index=0,
                timestamp_s=0.0,
            )

    def test_keeps_the_raw_detector_label_for_auditing(self) -> None:
        detection = Detection(
            vehicle_class=VehicleClass.PEDESTRIAN,
            confidence=0.8,
            box=box(0, 0, 10, 10),
            frame_index=3,
            timestamp_s=0.12,
            raw_class_name="person",
        )
        assert detection.raw_class_name == "person"


class TestTrack:
    def make_track(self) -> Track:
        track = Track(track_id=104, vehicle_class=VehicleClass.CAR)
        for index, (x, y) in enumerate([(100, 400), (100, 380), (100, 350), (100, 300)]):
            track.add_point(
                TrackPoint(
                    frame_index=index,
                    timestamp_s=index * 0.04,
                    box=box(x - 10, y - 20, x + 10, y),
                    confidence=0.9,
                ),
                observed_class=VehicleClass.CAR,
            )
        return track

    def test_reports_its_frame_span_and_duration(self) -> None:
        track = self.make_track()
        assert track.first_seen_frame == 0
        assert track.last_seen_frame == 3
        assert track.duration_s == pytest.approx(0.12)

    def test_empty_track_has_no_frame_span(self) -> None:
        track = Track(track_id=1, vehicle_class=VehicleClass.CAR)
        assert track.latest is None
        assert track.duration_s == 0.0
        with pytest.raises(ValueError, match="has no points"):
            _ = track.first_seen_frame

    def test_displacement_and_path_length(self) -> None:
        track = self.make_track()
        # Straight-line motion: displacement equals path length.
        assert track.displacement_px() == pytest.approx(100.0)
        assert track.path_length_px() == pytest.approx(100.0)

    def test_path_length_exceeds_displacement_when_turning(self) -> None:
        track = Track(track_id=2, vehicle_class=VehicleClass.CAR)
        for index, (x, y) in enumerate([(0, 0), (100, 0), (100, 100)]):
            track.add_point(
                TrackPoint(frame_index=index, timestamp_s=index * 0.1, box=box(x, y, x + 1, y + 1), confidence=0.8)
            )
        assert track.path_length_px() == pytest.approx(200.0)
        assert track.displacement_px() == pytest.approx(math.hypot(100, 100))

    def test_class_is_decided_by_majority_vote(self) -> None:
        """A single misread frame must not change a track's class."""
        track = Track(track_id=3, vehicle_class=VehicleClass.MOTORCYCLE)
        for index in range(5):
            observed = VehicleClass.BICYCLE if index == 2 else VehicleClass.MOTORCYCLE
            track.add_point(
                TrackPoint(frame_index=index, timestamp_s=index * 0.04, box=box(0, 0, 10, 10), confidence=0.7),
                observed_class=observed,
            )
        assert track.vehicle_class is VehicleClass.MOTORCYCLE
        assert track.class_votes[VehicleClass.BICYCLE] == 1

    def test_visual_checks_default_to_undetermined(self) -> None:
        """A fresh track has made no determination, which is not a negative."""
        track = Track(track_id=4, vehicle_class=VehicleClass.MOTORCYCLE)
        assert track.helmet is Determination.UNABLE_TO_DETERMINE
        assert track.seatbelt is Determination.UNABLE_TO_DETERMINE
        assert track.occupant_count is None


class TestClassMapping:
    def test_maps_known_coco_labels_case_insensitively(self) -> None:
        assert map_detector_class("Car") is VehicleClass.CAR
        assert map_detector_class("  MOTORCYCLE ") is VehicleClass.MOTORCYCLE
        assert map_detector_class("person") is VehicleClass.PEDESTRIAN

    def test_unmapped_label_returns_none_rather_than_a_guess(self) -> None:
        # COCO cannot distinguish these, so the stock mapping must not claim to.
        assert map_detector_class("auto-rickshaw") is None
        assert map_detector_class("scooter") is None
        assert map_detector_class("aeroplane") is None

    def test_every_mapped_target_is_a_real_contract_class(self) -> None:
        for mapped in COCO_TO_VEHICLE_CLASS.values():
            assert mapped in set(VehicleClass)

    def test_a_custom_mapping_can_extend_the_taxonomy(self) -> None:
        custom = {"tuktuk": VehicleClass.AUTO_RICKSHAW}
        assert map_detector_class("tuktuk", custom) is VehicleClass.AUTO_RICKSHAW
