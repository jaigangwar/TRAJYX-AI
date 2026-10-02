"""The single feature builder used to prepare training rows and serve predictions."""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timezone
from typing import Any

FEATURE_NAMES = (
    "near_miss_per_hour", "violation_per_hour", "hard_braking_per_hour",
    "wrong_way_per_hour", "pedestrian_conflict_per_hour", "collision_risk_per_hour",
    "minimum_ttc_s", "minimum_ttc_missing", "mean_ttc_s", "mean_ttc_missing",
    "vehicles_per_hour", "vehicles_per_hour_missing", "pedestrians_per_hour",
    "pedestrians_per_hour_missing", "car_share", "car_share_missing",
    "motorcycle_share", "motorcycle_share_missing", "bus_truck_share",
    "bus_truck_share_missing", "segment_length_m", "segment_length_missing",
    "lanes", "lanes_missing", "speed_limit_kmh", "speed_limit_missing",
    "one_way", "hour_sin", "hour_cos", "weekday_sin", "weekday_cos",
    "analysis_coverage_missing", "helmet_check_covered", "wrong_way_check_covered",
    "red_light_check_covered",
)

_EVENT_GROUPS = {
    "near_miss_per_hour": {"NEAR_MISS"},
    "violation_per_hour": {
        "HELMET_VIOLATION", "SEATBELT_VIOLATION", "TRIPLE_RIDING", "WRONG_WAY",
        "RED_LIGHT_VIOLATION", "STOP_LINE_VIOLATION", "DANGEROUS_LANE_CHANGE", "OVERSPEED",
    },
    "hard_braking_per_hour": {"HARD_BRAKING", "SUDDEN_ACCELERATION"},
    "wrong_way_per_hour": {"WRONG_WAY"},
    "pedestrian_conflict_per_hour": {"PEDESTRIAN_CONFLICT"},
    "collision_risk_per_hour": {"COLLISION_RISK"},
}


UTC = timezone.utc


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and math.isfinite(float(value)) else None


def _length_m(path: list[Any] | None) -> float | None:
    points = [point for point in (path or []) if isinstance(point, dict)]
    if len(points) < 2:
        return None
    total = 0.0
    for start, end in zip(points, points[1:]):
        try:
            lat1, lon1 = math.radians(float(start["latitude"])), math.radians(float(start["longitude"]))
            lat2, lon2 = math.radians(float(end["latitude"])), math.radians(float(end["longitude"]))
        except (KeyError, TypeError, ValueError):
            return None
        dlat, dlon = lat2 - lat1, lon2 - lon1
        hav = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        total += 6_371_000 * 2 * math.asin(math.sqrt(min(1.0, hav)))
    return total


def build_feature_row(
    *,
    segment: dict[str, Any],
    events: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
    window_start: datetime,
    window_end: datetime,
) -> dict[str, float]:
    """Build a fixed numeric feature vector from stored domain records.

    Missing observations stay NaN and get a companion flag. They are never
    silently changed to zero, which would assert that a missing detector saw
    no events.
    """
    start = _timestamp(window_start)
    end = _timestamp(window_end)
    if start is None or end is None or end <= start:
        raise ValueError("window_end must be later than window_start")
    hours = (end - start).total_seconds() / 3600

    scoped_events = [
        event for event in events
        if event.get("road_segment_id") == segment.get("id")
        and (timestamp := _timestamp(event.get("timestamp"))) is not None
        and start <= timestamp < end
    ]
    counts = Counter(str(event.get("event_type", "")) for event in scoped_events)
    features: dict[str, float] = {}
    for name, event_types in _EVENT_GROUPS.items():
        features[name] = sum(counts[event_type] for event_type in event_types) / hours

    ttc_values = [
        value
        for event in scoped_events
        if (value := _number((event.get("details") if isinstance(event.get("details"), dict) else {}).get("estimated_ttc_seconds"))) is not None
        and value >= 0
    ]
    features["minimum_ttc_s"] = min(ttc_values) if ttc_values else math.nan
    features["minimum_ttc_missing"] = float(not ttc_values)
    features["mean_ttc_s"] = sum(ttc_values) / len(ttc_values) if ttc_values else math.nan
    features["mean_ttc_missing"] = float(not ttc_values)

    scoped_analyses = [
        analysis for analysis in analyses
        if (timestamp := _timestamp(analysis.get("created_at"))) is not None
        and start <= timestamp < end
    ]
    classes: Counter[str] = Counter()
    for analysis in scoped_analyses:
        raw_counts = analysis.get("class_counts")
        if isinstance(raw_counts, dict):
        classes.update({
            str(key).upper(): max(0, int(value))
            for key, value in raw_counts.items()
            if isinstance(value, int | float) and math.isfinite(float(value))
        })
    total = sum(classes.values())
    vehicle_count = sum(max(0, int(analysis.get("vehicle_count", 0) or 0)) for analysis in scoped_analyses)
    pedestrians = sum(max(0, int(analysis.get("pedestrian_count", 0) or 0)) for analysis in scoped_analyses)
    features["vehicles_per_hour"] = vehicle_count / hours if scoped_analyses else math.nan
    features["vehicles_per_hour_missing"] = float(not scoped_analyses)
    features["pedestrians_per_hour"] = pedestrians / hours if scoped_analyses else math.nan
    features["pedestrians_per_hour_missing"] = float(not scoped_analyses)
    class_groups = {
        "car_share": {"CAR", "VAN"},
        "motorcycle_share": {"MOTORCYCLE", "SCOOTER"},
        "bus_truck_share": {"BUS", "TRUCK"},
    }
    for name, labels in class_groups.items():
        missing = total == 0
        features[name] = sum(classes[label] for label in labels) / total if not missing else math.nan
        features[f"{name}_missing"] = float(missing)

    length = _number(segment.get("length_m")) or _length_m(segment.get("path", []))
    lanes = _number(segment.get("lanes"))
    speed_limit = _number(segment.get("speed_limit_kmh"))
    features["segment_length_m"] = length if length is not None else math.nan
    features["segment_length_missing"] = float(length is None)
    features["lanes"] = lanes if lanes is not None else math.nan
    features["lanes_missing"] = float(lanes is None)
    features["speed_limit_kmh"] = speed_limit if speed_limit is not None else math.nan
    features["speed_limit_missing"] = float(speed_limit is None)
    features["one_way"] = float(bool(segment.get("one_way", False)))

    hour_angle = 2 * math.pi * (start.hour + start.minute / 60) / 24
    weekday_angle = 2 * math.pi * start.weekday() / 7
    features.update({
        "hour_sin": math.sin(hour_angle), "hour_cos": math.cos(hour_angle),
        "weekday_sin": math.sin(weekday_angle), "weekday_cos": math.cos(weekday_angle),
    })

    unavailable: set[str] = set()
    covered_checks = 0
    for analysis in scoped_analyses:
        for check in analysis.get("unavailable_checks", []):
            if isinstance(check, dict) and isinstance(check.get("name"), str):
                unavailable.add(check["name"].lower())
        covered_checks += 1
    features["analysis_coverage_missing"] = float(covered_checks == 0)
    features["helmet_check_covered"] = float(covered_checks > 0 and not any("helmet" in name for name in unavailable))
    features["wrong_way_check_covered"] = float(covered_checks > 0 and not any("wrong_way" in name for name in unavailable))
    features["red_light_check_covered"] = float(covered_checks > 0 and not any("red_light" in name for name in unavailable))
    return {name: features[name] for name in FEATURE_NAMES}
