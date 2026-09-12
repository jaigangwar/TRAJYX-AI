"""Seed demo data: cameras, road segments, events, risk zones, a driver.

    python scripts/seed_demo.py
    python scripts/seed_demo.py --purge      # remove demo records only

Everything written carries ``origin=DEMO``. The dashboard labels it, the
`origin=MEASURED` filter excludes it, and any risk zone derived from it is
tagged DEMO too — so a demo run can never be mistaken for measured traffic.

`--purge` deletes only records tagged DEMO, so it is safe to run against a
deployment that also holds real data.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# A corridor through Delhi/Gurugram, used because the coordinates are real and
# the geometry is plausible. No claim is made about actual risk at these places.
CORRIDOR = [
    {
        "name": "Ring Road / Sector 12 junction",
        "road_name": "Outer Ring Road",
        "path": [
            {"latitude": 28.6139, "longitude": 77.2090},
            {"latitude": 28.6152, "longitude": 77.2128},
            {"latitude": 28.6168, "longitude": 77.2171},
        ],
        "speed_limit_kmh": 50,
        "lanes": 3,
        "profile": "critical",
    },
    {
        "name": "NH-48 toll approach",
        "road_name": "NH-48",
        "path": [
            {"latitude": 28.4595, "longitude": 77.0266},
            {"latitude": 28.4631, "longitude": 77.0305},
            {"latitude": 28.4672, "longitude": 77.0349},
        ],
        "speed_limit_kmh": 70,
        "lanes": 4,
        "profile": "high",
    },
    {
        "name": "Sector 29 market crossing",
        "road_name": "Dr Jai Prakash Marg",
        "path": [
            {"latitude": 28.4698, "longitude": 77.0721},
            {"latitude": 28.4715, "longitude": 77.0748},
        ],
        "speed_limit_kmh": 40,
        "lanes": 2,
        "profile": "moderate",
    },
    {
        "name": "Golf Course Road flyover",
        "road_name": "Golf Course Road",
        "path": [
            {"latitude": 28.4421, "longitude": 77.0982},
            {"latitude": 28.4468, "longitude": 77.1018},
            {"latitude": 28.4510, "longitude": 77.1051},
        ],
        "speed_limit_kmh": 60,
        "lanes": 3,
        "profile": "low",
    },
]

#: Events **per day**, per profile, for a camera observing continuously.
#:
#: Expressed per day rather than per window on purpose: the risk engine works
#: in rates, and an earlier version of this script gave per-window totals, so a
#: "critical" junction came out at one near miss a day and scored LOW. These
#: figures are what continuous monitoring of a genuinely conflict-prone
#: junction would plausibly record.
PROFILES_PER_DAY = {
    "critical": {
        "NEAR_MISS": 12,
        "WRONG_WAY": 3,
        "HARD_BRAKING": 26,
        "PEDESTRIAN_CONFLICT": 6,
        "DANGEROUS_LANE_CHANGE": 9,
        "OVERSPEED": 7,
        "SUDDEN_ACCELERATION": 11,
    },
    "high": {
        "NEAR_MISS": 5,
        "HARD_BRAKING": 16,
        "OVERSPEED": 14,
        "DANGEROUS_LANE_CHANGE": 5,
        "SUDDEN_ACCELERATION": 7,
    },
    "moderate": {
        "NEAR_MISS": 1,
        "PEDESTRIAN_CONFLICT": 2,
        "HARD_BRAKING": 5,
        "STOP_LINE_VIOLATION": 2,
    },
    "low": {"HARD_BRAKING": 1, "SUDDEN_ACCELERATION": 1},
}

#: Weighting by hour. Peaks at the morning and evening commutes, which is what
#: makes the time-of-day risk charts show something real.
HOUR_WEIGHTS = [
    1, 1, 1, 1, 1, 2, 4, 7, 9, 7, 5, 5,
    5, 5, 5, 6, 8, 12, 14, 12, 8, 5, 3, 2,
]


async def purge(store) -> dict[str, int]:  # noqa: ANN001
    """Delete only records tagged DEMO."""
    from app.repositories.base import Filter, Query
    from trajyx_shared.domain import DataOrigin

    removed: dict[str, int] = {}
    for collection in ("risk_events", "risk_zones", "video_jobs", "video_analysis", "alerts"):
        page = await store.query(
            collection, Query().where(Filter.eq("origin", DataOrigin.DEMO.value))
        )
        for document in page.documents:
            await store.delete(collection, str(document["id"]))
        removed[collection] = len(page.documents)

    # Demo cameras and segments are marked with a flag rather than an origin,
    # since those collections have no origin field.
    for collection in ("cameras", "road_segments"):
        page = await store.query(collection, Query().where(Filter.eq("is_demo", True)))
        for document in page.documents:
            await store.delete(collection, str(document["id"]))
        removed[collection] = len(page.documents)

    return removed


async def run(purge_only: bool, days: int) -> int:
    from app.core.config import get_settings
    from app.geo.service import GeoService
    from app.geo.spatial import LatLon, polyline_bearing, polyline_length_m
    from app.repositories.base import utc_now
    from app.repositories.factory import create_document_store
    from trajyx_shared.domain import EVENT_CATEGORY, DataOrigin, EventType

    settings = get_settings()
    store = create_document_store(settings)

    print(f"data backend : {settings.resolved_data_backend.value}")
    print(f"demo mode    : {settings.demo_mode}\n")

    if not settings.demo_mode and not purge_only:
        print(
            "Demo mode is disabled for this deployment (TRAJYX_DEMO_MODE=false). "
            "Refusing to write demo records.",
            file=sys.stderr,
        )
        return 1

    removed = await purge(store)
    print("purged demo records:", {k: v for k, v in removed.items() if v})
    if purge_only:
        await store.close()
        return 0

    rng = random.Random(20260912)
    now = datetime.now(timezone.utc)
    created_segments = 0
    created_cameras = 0
    event_documents: list[dict] = []

    for entry in CORRIDOR:
        points = [LatLon(p["latitude"], p["longitude"]) for p in entry["path"]]

        segment = await store.create(
            "road_segments",
            {
                "name": entry["name"],
                "road_name": entry["road_name"],
                "path": entry["path"],
                "speed_limit_kmh": entry["speed_limit_kmh"],
                "lanes": entry["lanes"],
                "one_way": False,
                "length_m": round(polyline_length_m(points), 1),
                "bearing_deg": polyline_bearing(points),
                "risk_score": None,
                "event_count": 0,
                "is_demo": True,
                "created_at": utc_now(),
                "updated_at": utc_now(),
            },
        )
        segment_id = str(segment["id"])
        created_segments += 1

        # One camera at the midpoint, configured so wrong-way and speed
        # estimation are genuinely available.
        midpoint = entry["path"][len(entry["path"]) // 2]
        bearing = polyline_bearing(points) or 90.0
        await store.create(
            "cameras",
            {
                "name": f"{entry['name']} CAM",
                "road_name": entry["road_name"],
                "road_segment_id": segment_id,
                "location": midpoint,
                "status": "ONLINE",
                "signal_state": "UNKNOWN",
                "frame_width": 1920,
                "frame_height": 1080,
                "frame_rate": 25.0,
                "lane_directions": [
                    {
                        "lane_index": 0,
                        "heading_deg": round(bearing, 1),
                        "label": "Primary",
                        "region_y_min": 240,
                        "region_y_max": 520,
                    },
                    {
                        "lane_index": 1,
                        "heading_deg": round((bearing + 180) % 360, 1),
                        "label": "Opposing",
                        "region_y_min": 560,
                        "region_y_max": 900,
                    },
                ],
                "calibration": {
                    "metres_per_pixel_at_reference": 0.085,
                    "reference_y": 820.0,
                    "notes": "Demo calibration. Not surveyed.",
                },
                "current_risk_score": None,
                "last_seen_at": utc_now(),
                "is_demo": True,
                "created_at": utc_now(),
                "updated_at": utc_now(),
            },
        )
        created_cameras += 1

        # Spread events along the segment and across the window.
        for raw_type, per_day in PROFILES_PER_DAY[entry["profile"]].items():
            event_type = EventType(raw_type)
            for _ in range(per_day * days):
                hour = rng.choices(range(24), weights=HOUR_WEIGHTS, k=1)[0]
                day_offset = rng.randint(0, max(0, days - 1))
                timestamp = (now - timedelta(days=day_offset)).replace(
                    hour=hour, minute=rng.randint(0, 59), second=rng.randint(0, 59)
                )

                # Jitter within ~30 m of the segment so the weighted centroid
                # lands on the road rather than exactly on a vertex.
                anchor = entry["path"][rng.randrange(len(entry["path"]))]
                location = {
                    "latitude": anchor["latitude"] + rng.uniform(-0.00025, 0.00025),
                    "longitude": anchor["longitude"] + rng.uniform(-0.00025, 0.00025),
                }

                severity, risk, details = _event_payload(event_type, rng)
                event_documents.append(
                    {
                        "event_type": event_type.value,
                        "category": EVENT_CATEGORY[event_type].value,
                        "timestamp": timestamp,
                        "camera_id": None,
                        "road_segment_id": segment_id,
                        "location": location,
                        "severity": severity.value,
                        "confidence": round(rng.uniform(0.55, 0.95), 2),
                        "risk_score": risk,
                        "origin": DataOrigin.DEMO.value,
                        "model_version": "demo-seed-1.0",
                        "track_ids": [rng.randint(100, 999) for _ in range(rng.choice([1, 1, 2]))],
                        "details": details,
                        "review_status": "PENDING",
                        "created_at": utc_now(),
                    }
                )

    written = await store.bulk_create("risk_events", event_documents)
    print(f"created      : {created_segments} segments, {created_cameras} cameras, {written} events")

    result = await GeoService(store).aggregate(window_hours=24 * days)
    print(f"aggregated   : {result}")

    zones = await store.query("risk_zones")
    print("\nrisk zones:")
    for zone in sorted(
        zones.documents, key=lambda z: -float(z.get("risk_score", 0) or 0)
    ):
        print(
            f"  {zone.get('risk_score'):5.1f}  {zone.get('risk_level'):9}  "
            f"{zone.get('road_name')}  ({zone.get('event_count')} events, "
            f"peak {zone.get('peak_hour')}:00, origin {zone.get('origin')})"
        )

    await store.close()
    print("\nAll seeded records are tagged DEMO and labelled in both clients.")
    return 0


def _event_payload(event_type, rng):  # noqa: ANN001, ANN201
    from trajyx_shared.domain import EventType, Severity

    if event_type is EventType.NEAR_MISS:
        ttc = round(rng.uniform(0.3, 2.0), 2)
        return (
            Severity.CRITICAL if ttc < 1.0 else Severity.MAJOR,
            round(rng.uniform(62, 96), 1),
            {
                "estimated_ttc_seconds": ttc,
                "gap_metres": round(rng.uniform(0.8, 4.5), 2),
                "risk_factors": [
                    "Estimated time to collision under 1 second"
                    if ttc < 1
                    else f"Estimated time to collision {ttc:.1f} seconds",
                    "Trajectories converging",
                ],
                "measurement": "ESTIMATED",
            },
        )
    if event_type is EventType.WRONG_WAY:
        return (
            Severity.CRITICAL,
            round(rng.uniform(70, 92), 1),
            {
                "angular_difference_deg": round(rng.uniform(160, 180), 1),
                "duration_s": round(rng.uniform(3, 14), 1),
            },
        )
    if event_type is EventType.HARD_BRAKING:
        deceleration = round(rng.uniform(4.2, 8.8), 2)
        return (
            Severity.MAJOR if deceleration > 6 else Severity.MINOR,
            None,
            {"deceleration_ms2": deceleration, "threshold_ms2": 4.0},
        )
    if event_type is EventType.SUDDEN_ACCELERATION:
        return (
            Severity.MINOR,
            None,
            {"acceleration_ms2": round(rng.uniform(3.6, 7.5), 2), "threshold_ms2": 3.5},
        )
    if event_type is EventType.PEDESTRIAN_CONFLICT:
        return (
            Severity.CRITICAL,
            round(rng.uniform(68, 94), 1),
            {"separation_metres": round(rng.uniform(0.5, 2.4), 2), "measurement": "ESTIMATED"},
        )
    if event_type is EventType.OVERSPEED:
        return (
            Severity.MAJOR,
            None,
            {
                "estimated_speed_kmh": round(rng.uniform(62, 108), 1),
                "speed_limit_kmh": 50,
                "measurement": "ESTIMATED",
            },
        )
    if event_type is EventType.DANGEROUS_LANE_CHANGE:
        return (
            Severity.MINOR,
            None,
            {"lateral_displacement_px": round(rng.uniform(90, 210), 1)},
        )
    return (Severity.MINOR, None, {})


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed or purge TRAJYX demo data.")
    parser.add_argument("--purge", action="store_true", help="remove demo records and exit")
    parser.add_argument("--days", type=int, default=14, help="window to spread events over")
    args = parser.parse_args()
    return asyncio.run(run(args.purge, args.days))


if __name__ == "__main__":
    raise SystemExit(main())
