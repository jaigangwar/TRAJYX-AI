"""Road segments, risk-zone aggregation and the driver alert engine.

This is where observations become the thing the product actually promises: a
warning before the driver reaches a dangerous place.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

import structlog
from trajyx_shared.domain import (
    ALERT_DEFAULTS,
    EVENT_CATEGORY,
    AlertLevel,
    DataOrigin,
    EventCategory,
    EventType,
    RiskLevel,
    risk_level_from_score,
)

from app.core.errors import ConflictError, NotFoundError
from app.geo.spatial import (
    LatLon,
    bearing_deg,
    bounding_box_around,
    distance_to_polyline,
    haversine_m,
    is_ahead,
    polyline_bearing,
    polyline_length_m,
)
from app.repositories.base import DocumentStore, Filter, Query, utc_now
from app.risk.engine import RiskInputs, assess
from app.schemas.geo import (
    AlertEvaluationResponse,
    AlertResponse,
    HourlyRiskPoint,
    NearbyRiskRequest,
    NearbyZone,
    RiskZoneResponse,
    RoadSegmentCreate,
    RoadSegmentResponse,
    RoadSegmentUpdate,
    SegmentDetailResponse,
)

log = structlog.get_logger(__name__)

SEGMENTS = "road_segments"
ZONES = "risk_zones"
EVENTS = "risk_events"
CAMERAS = "cameras"
ALERTS = "alerts"

#: How far from a segment an event can be and still be attributed to it.
#: Roughly one carriageway plus GPS error.
EVENT_ATTRIBUTION_RADIUS_M = 60.0

#: Influence radius of a generated risk zone. A driver should be warned while
#: still able to react, so the zone itself is modest and the *approach*
#: distance in ALERT_DEFAULTS does the early warning.
ZONE_RADIUS_M = 140.0


class GeoService:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    # ------------------------------------------------------------- segments

    async def create_segment(self, payload: RoadSegmentCreate) -> RoadSegmentResponse:
        existing = await self._store.query(
            SEGMENTS, Query().where(Filter.eq("name", payload.name)).take(1)
        )
        if existing.documents:
            raise ConflictError(f"A road segment named {payload.name!r} already exists.")

        points = [LatLon(point.latitude, point.longitude) for point in payload.path]
        document = await self._store.create(
            SEGMENTS,
            {
                **payload.model_dump(mode="json"),
                "length_m": round(polyline_length_m(points), 1),
                "bearing_deg": polyline_bearing(points),
                "risk_score": None,
                "event_count": 0,
                "near_miss_count": 0,
                "violation_count": 0,
                "top_risk_factors": [],
                "created_at": utc_now(),
                "updated_at": utc_now(),
            },
        )
        return RoadSegmentResponse.from_document(document)

    async def get_segment(self, segment_id: str) -> RoadSegmentResponse:
        document = await self._store.get(SEGMENTS, segment_id)
        if document is None:
            raise NotFoundError(
                f"Road segment {segment_id} not found.", details={"segment_id": segment_id}
            )
        return RoadSegmentResponse.from_document(document)

    async def list_segments(
        self, minimum_risk: float | None = None, limit: int = 200
    ) -> list[RoadSegmentResponse]:
        query = Query().take(limit)
        if minimum_risk is not None:
            query = query.where(Filter.gte("risk_score", minimum_risk))

        page = await self._store.query(SEGMENTS, query)
        segments = [RoadSegmentResponse.from_document(item) for item in page.documents]
        # Riskiest first: the map and the table both want the problems on top.
        segments.sort(key=lambda item: item.risk_score or -1.0, reverse=True)
        return segments

    async def update_segment(
        self, segment_id: str, payload: RoadSegmentUpdate
    ) -> RoadSegmentResponse:
        await self.get_segment(segment_id)
        changes = payload.model_dump(mode="json", exclude_unset=True)
        if not changes:
            return await self.get_segment(segment_id)

        if "path" in changes and changes["path"]:
            points = [LatLon(p["latitude"], p["longitude"]) for p in changes["path"]]
            changes["length_m"] = round(polyline_length_m(points), 1)
            changes["bearing_deg"] = polyline_bearing(points)

        document = await self._store.update(
            SEGMENTS, segment_id, {**changes, "updated_at": utc_now()}
        )
        return RoadSegmentResponse.from_document(document)

    async def delete_segment(self, segment_id: str) -> None:
        await self.get_segment(segment_id)
        await self._store.delete(SEGMENTS, segment_id)
        # Zones derived from it are stale, so drop them; they will be
        # recomputed from events on the next aggregation.
        zones = await self._store.query(
            ZONES, Query().where(Filter.eq("road_segment_id", segment_id))
        )
        for zone in zones.documents:
            await self._store.delete(ZONES, str(zone["id"]))

    # ----------------------------------------------------------- attribution

    async def attribute_events(self) -> int:
        """Assign unattributed located events to their nearest road segment.

        Runs as part of aggregation. An event keeps its own coordinates, so
        re-attribution after a segment edit is possible; the segment id is a
        derived convenience, not the source of truth.
        """
        segments = await self._store.query(SEGMENTS)
        if not segments.documents:
            return 0

        polylines: list[tuple[str, list[LatLon]]] = []
        for document in segments.documents:
            points = [
                LatLon(float(p["latitude"]), float(p["longitude"]))
                for p in document.get("path", [])
                if isinstance(p, dict)
            ]
            if len(points) >= 2:
                polylines.append((str(document["id"]), points))

        events = await self._store.query(EVENTS)
        attributed = 0

        for event in events.documents:
            if event.get("road_segment_id"):
                continue
            location = event.get("location")
            if not isinstance(location, dict):
                continue

            point = LatLon(float(location["latitude"]), float(location["longitude"]))
            best_id: str | None = None
            best_distance = EVENT_ATTRIBUTION_RADIUS_M

            for segment_id, polyline in polylines:
                projection = distance_to_polyline(point, polyline)
                if projection and projection.distance_m <= best_distance:
                    best_distance = projection.distance_m
                    best_id = segment_id

            if best_id:
                await self._store.update(EVENTS, str(event["id"]), {"road_segment_id": best_id})
                attributed += 1

        if attributed:
            log.info("geo.events_attributed", count=attributed)
        return attributed

    # ----------------------------------------------------------- aggregation

    async def aggregate(self, window_hours: int = 24 * 7) -> dict[str, int]:
        """Recompute segment risk and risk zones from attributed events.

        Zones are always derived from events. A hand-placed hazard would be an
        opinion presented as a measurement, and the driver app cannot tell the
        difference.
        """
        await self.attribute_events()

        since = utc_now() - timedelta(hours=window_hours)
        page = await self._store.query(EVENTS, Query().where(Filter.gte("timestamp", since)))

        by_segment: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in page.documents:
            segment_id = event.get("road_segment_id")
            if segment_id:
                by_segment[str(segment_id)].append(event)

        segments = await self._store.query(SEGMENTS)
        segment_lookup = {str(item["id"]): item for item in segments.documents}

        # Clear zones first so a segment that has gone quiet stops warning
        # drivers about a hazard that is no longer observed.
        existing_zones = await self._store.query(ZONES)
        for zone in existing_zones.documents:
            await self._store.delete(ZONES, str(zone["id"]))

        zones_created = 0
        segments_scored = 0

        for segment_id, document in segment_lookup.items():
            events = by_segment.get(segment_id, [])
            inputs, breakdown = _risk_inputs(events, window_hours)
            assessment = assess(inputs)

            peak_hour = _peak_hour(events)
            has_demo = any(
                str(event.get("origin")) == DataOrigin.DEMO.value for event in events
            )

            await self._store.update(
                SEGMENTS,
                segment_id,
                {
                    "risk_score": assessment.score if events else None,
                    "risk_confidence": assessment.confidence if events else None,
                    "event_count": len(events),
                    "near_miss_count": breakdown.get(EventType.NEAR_MISS.value, 0),
                    "violation_count": sum(
                        count
                        for key, count in breakdown.items()
                        if EVENT_CATEGORY.get(EventType(key)) is EventCategory.VIOLATION
                    ),
                    "top_risk_factors": assessment.explain(),
                    "peak_hour": peak_hour,
                    "last_event_at": _latest_timestamp(events),
                    "updated_at": utc_now(),
                },
            )
            segments_scored += 1

            # Only genuinely elevated segments become zones. Warning a driver
            # about a low-risk stretch trains them to ignore the app.
            if not events or assessment.level is RiskLevel.LOW:
                continue

            centre = _event_centroid(events) or _segment_midpoint(document)
            if centre is None:
                continue

            dominant = Counter(str(event.get("event_type")) for event in events).most_common(1)
            await self._store.create(
                ZONES,
                {
                    "road_segment_id": segment_id,
                    "road_name": document.get("road_name") or document.get("name"),
                    "centre": {"latitude": centre.latitude, "longitude": centre.longitude},
                    "radius_m": ZONE_RADIUS_M,
                    "risk_score": assessment.score,
                    "risk_level": assessment.level.value,
                    "confidence": assessment.confidence,
                    "top_risk_factors": assessment.explain(),
                    "event_count": len(events),
                    "near_miss_count": breakdown.get(EventType.NEAR_MISS.value, 0),
                    "violation_count": sum(
                        count
                        for key, count in breakdown.items()
                        if EVENT_CATEGORY.get(EventType(key)) is EventCategory.VIOLATION
                    ),
                    "dominant_event_type": dominant[0][0] if dominant else None,
                    "peak_hour": peak_hour,
                    "bearing_deg": document.get("bearing_deg"),
                    "computed_at": utc_now(),
                    "window_hours": window_hours,
                    # A zone built from demo events must say so, or a demo run
                    # would produce warnings indistinguishable from real ones.
                    "origin": DataOrigin.DEMO.value if has_demo else DataOrigin.MEASURED.value,
                },
            )
            zones_created += 1

        log.info(
            "geo.aggregated",
            segments=segments_scored,
            zones=zones_created,
            window_hours=window_hours,
        )
        return {"segments_scored": segments_scored, "zones_created": zones_created}

    async def list_zones(
        self, minimum_level: RiskLevel | None = None
    ) -> list[RiskZoneResponse]:
        page = await self._store.query(ZONES)
        zones = [RiskZoneResponse.from_document(item) for item in page.documents]

        if minimum_level is not None:
            order = [RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH, RiskLevel.CRITICAL]
            floor = order.index(minimum_level)
            zones = [zone for zone in zones if order.index(zone.risk_level) >= floor]

        zones.sort(key=lambda zone: zone.risk_score, reverse=True)
        return zones

    async def segment_detail(self, segment_id: str) -> SegmentDetailResponse:
        segment = await self.get_segment(segment_id)

        page = await self._store.query(
            EVENTS,
            Query().where(Filter.eq("road_segment_id", segment_id)).order_by("timestamp", descending=True),
        )
        events = page.documents

        breakdown = Counter(str(event.get("event_type")) for event in events)

        # Risk scored per hour: the same junction is quiet at 06:00 and
        # dangerous at 19:00, and a single number hides that.
        by_hour: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            timestamp = event.get("timestamp")
            if isinstance(timestamp, datetime):
                by_hour[timestamp.hour].append(event)

        hourly: list[HourlyRiskPoint] = []
        for hour in sorted(by_hour):
            inputs, _ = _risk_inputs(by_hour[hour], window_hours=1)
            inputs.hour_of_day = hour
            assessment = assess(inputs)
            hourly.append(
                HourlyRiskPoint(
                    hour=hour,
                    risk_score=assessment.score,
                    risk_level=assessment.level,
                    event_count=len(by_hour[hour]),
                )
            )

        cameras = await self._store.query(
            CAMERAS, Query().where(Filter.eq("road_segment_id", segment_id))
        )

        return SegmentDetailResponse(
            segment=segment,
            risk_by_hour=hourly,
            event_breakdown=dict(breakdown),
            recent_events=[
                {
                    "id": str(event["id"]),
                    "event_type": event.get("event_type"),
                    "timestamp": event.get("timestamp"),
                    "severity": event.get("severity"),
                    "risk_score": event.get("risk_score"),
                    "origin": event.get("origin"),
                }
                for event in events[:10]
            ],
            cameras=[
                {"id": str(camera["id"]), "name": camera.get("name"), "status": camera.get("status")}
                for camera in cameras.documents
            ],
        )

    # ---------------------------------------------------------- alert engine

    async def evaluate_alert(
        self, request: NearbyRiskRequest, user_id: str | None = None
    ) -> AlertEvaluationResponse:
        """Decide whether this driver should be warned, and how.

        Four gates, all of which must pass. Each exists because failing it
        produces an alert the driver will learn to ignore:

        1. **Distance** — the zone must be within the approach distance for
           its level, so the warning arrives with time to react.
        2. **Direction** — the zone must be ahead. Warning about a hazard
           already passed, or one on a parallel road going the other way, is
           the fastest way to make a safety app annoying.
        3. **Threshold** — the risk must clear the level's minimum score.
        4. **Cooldown** — the same zone must not re-alert within its window.
        """
        position = LatLon(request.latitude, request.longitude)
        box = bounding_box_around(position, request.radius_m)

        zones_page = await self._store.query(ZONES)
        nearby: list[NearbyZone] = []

        for document in zones_page.documents:
            centre = document.get("centre")
            if not isinstance(centre, dict):
                continue
            zone_point = LatLon(float(centre["latitude"]), float(centre["longitude"]))

            # Cheap box rejection before the trig.
            if not box.contains(zone_point):
                continue

            distance = haversine_m(position, zone_point)
            if distance > request.radius_m:
                continue

            zone = RiskZoneResponse.from_document(document)
            to_zone = bearing_deg(position, zone_point)
            ahead = (
                is_ahead(
                    position,
                    request.heading_deg,
                    zone_point,
                    float(ALERT_DEFAULTS["bearing_tolerance_deg"]),
                )
                if request.heading_deg is not None
                else True
            )

            eta: float | None = None
            if request.speed_kmh and request.speed_kmh > 1:
                eta = round(distance / (request.speed_kmh / 3.6), 1)

            nearby.append(
                NearbyZone(
                    zone=zone,
                    distance_m=round(distance, 1),
                    bearing_deg=round(to_zone, 1),
                    is_ahead=ahead,
                    eta_seconds=eta,
                )
            )

        nearby.sort(key=lambda item: item.distance_m)

        segment_id, segment_name = await self._match_segment(position, request.heading_deg)
        alert, suppressed = await self._choose_alert(nearby, request, user_id)

        return AlertEvaluationResponse(
            evaluated_at=utc_now(),
            position={"latitude": request.latitude, "longitude": request.longitude},  # type: ignore[arg-type]
            heading_deg=request.heading_deg,
            current_segment_id=segment_id,
            current_segment_name=segment_name,
            nearby=nearby,
            alert=alert,
            suppressed_reason=suppressed,
        )

    async def _match_segment(
        self, position: LatLon, heading: float | None
    ) -> tuple[str | None, str | None]:
        """Map-match the driver to a road segment.

        Distance alone is not enough where carriageways run close together, so
        a segment whose direction opposes the driver's heading is penalised
        rather than chosen.
        """
        page = await self._store.query(SEGMENTS)
        best: tuple[float, str, str] | None = None

        for document in page.documents:
            points = [
                LatLon(float(p["latitude"]), float(p["longitude"]))
                for p in document.get("path", [])
                if isinstance(p, dict)
            ]
            if len(points) < 2:
                continue

            projection = distance_to_polyline(position, points)
            if projection is None or projection.distance_m > 80.0:
                continue

            cost = projection.distance_m
            segment_bearing = document.get("bearing_deg")
            if heading is not None and isinstance(segment_bearing, int | float):
                from app.geo.spatial import angular_difference

                difference = angular_difference(heading, float(segment_bearing))
                # A two-way segment is equally valid in reverse, so fold the
                # difference; a one-way segment going the other way is penalised.
                if not document.get("one_way"):
                    difference = min(difference, 180.0 - difference)
                cost += difference * 0.6

            if best is None or cost < best[0]:
                best = (cost, str(document["id"]), str(document.get("name", "")))

        return (best[1], best[2]) if best else (None, None)

    async def _choose_alert(
        self, nearby: list[NearbyZone], request: NearbyRiskRequest, user_id: str | None
    ) -> tuple[AlertResponse | None, str | None]:
        if not nearby:
            return None, None

        candidates = [item for item in nearby if item.is_ahead]
        if not candidates:
            return None, "All nearby risk zones are behind the driver or off their heading."

        # Highest risk first; a critical zone slightly further away matters
        # more than a moderate one just ahead.
        candidates.sort(key=lambda item: (-item.zone.risk_score, item.distance_m))
        best = candidates[0]
        score = best.zone.risk_score

        level = _alert_level_for(score)
        if level is None:
            return None, f"Nearest zone ahead scores {score:.0f}, below the alert threshold."

        approach = float(ALERT_DEFAULTS["approach_distance_m"][level.value])
        if best.distance_m > approach:
            return None, (
                f"Zone is {best.distance_m:.0f} m away; {level.value} alerts are raised within "
                f"{approach:.0f} m."
            )

        cooldown = int(ALERT_DEFAULTS["cooldown_seconds"][level.value])
        if user_id and await self._within_cooldown(user_id, best.zone.id, cooldown):
            return None, f"Already alerted for this zone within the last {cooldown}s."

        return (
            AlertResponse(
                zone_id=best.zone.id,
                level=level,
                risk_score=score,
                risk_level=best.zone.risk_level,
                distance_m=best.distance_m,
                road_name=best.zone.road_name,
                headline=_headline(level),
                detail=_detail(best),
                factors=list(best.zone.top_risk_factors),
                recommendations=_recommendations(level, best.zone),
                cooldown_seconds=cooldown,
                origin=best.zone.origin,
            ),
            None,
        )

    async def _within_cooldown(self, user_id: str, zone_id: str, cooldown_seconds: int) -> bool:
        """Whether this driver was already warned about this zone recently.

        Without this the app fires on every GPS update — several times a
        second — which is the single fastest way to get a safety warning
        muted permanently.
        """
        page = await self._store.query(
            ALERTS,
            Query()
            .where(Filter.eq("user_id", user_id), Filter.eq("zone_id", zone_id))
            .order_by("created_at", descending=True)
            .take(1),
        )
        if not page.documents:
            return False

        created = page.documents[0].get("created_at")
        if not isinstance(created, datetime):
            return False
        return (utc_now() - created).total_seconds() < cooldown_seconds

    async def record_alert(self, alert: AlertResponse, user_id: str) -> str:
        document = await self._store.create(
            ALERTS,
            {
                "user_id": user_id,
                "zone_id": alert.zone_id,
                "level": alert.level.value,
                "risk_score": alert.risk_score,
                "risk_level": alert.risk_level.value,
                "distance_m": alert.distance_m,
                "road_name": alert.road_name,
                "headline": alert.headline,
                "factors": alert.factors,
                "origin": alert.origin,
                "created_at": utc_now(),
            },
        )
        return str(document["id"])


# -------------------------------------------------------------------- helpers


def _alert_level_for(score: float) -> AlertLevel | None:
    if score >= float(ALERT_DEFAULTS["level_3_min_risk"]):
        return AlertLevel.LEVEL_3
    if score >= float(ALERT_DEFAULTS["level_2_min_risk"]):
        return AlertLevel.LEVEL_2
    if score >= float(ALERT_DEFAULTS["level_1_min_risk"]):
        return AlertLevel.LEVEL_1
    return None


def _headline(level: AlertLevel) -> str:
    """The spoken line. Short, specific, and escalating in urgency."""
    return {
        AlertLevel.LEVEL_1: "Accident-prone zone ahead.",
        AlertLevel.LEVEL_2: "High-risk area ahead. Stay alert.",
        AlertLevel.LEVEL_3: "High collision risk ahead. Slow down.",
    }[level]


def _detail(nearby: NearbyZone) -> str:
    parts = [f"{nearby.distance_m:.0f} m ahead"]
    if nearby.zone.road_name:
        parts.append(f"on {nearby.zone.road_name}")
    if nearby.eta_seconds is not None:
        parts.append(f"about {nearby.eta_seconds:.0f}s away")
    return ", ".join(parts) + "."


def _recommendations(level: AlertLevel, zone: RiskZoneResponse) -> list[str]:
    """Actionable advice, tailored to what was actually observed there."""
    advice: list[str] = []
    if level is AlertLevel.LEVEL_3:
        advice.append("Reduce speed now")
    elif level is AlertLevel.LEVEL_2:
        advice.append("Reduce speed")
    advice.append("Stay alert")

    dominant = zone.dominant_event_type
    if dominant is EventType.PEDESTRIAN_CONFLICT:
        advice.append("Watch for people crossing")
    elif dominant is EventType.WRONG_WAY:
        advice.append("Watch for oncoming vehicles in your lane")
    elif dominant in {EventType.NEAR_MISS, EventType.COLLISION_RISK}:
        advice.append("Increase your following distance")
    elif dominant is EventType.HARD_BRAKING:
        advice.append("Expect sudden braking ahead")
    elif dominant is EventType.DANGEROUS_LANE_CHANGE:
        advice.append("Watch for vehicles changing lanes")

    return advice


def _risk_inputs(
    events: list[dict[str, Any]], window_hours: int
) -> tuple[RiskInputs, dict[str, int]]:
    breakdown = Counter(str(event.get("event_type")) for event in events)

    ttcs = [
        float(details["estimated_ttc_seconds"])
        for event in events
        if isinstance(details := event.get("details"), dict)
        and isinstance(details.get("estimated_ttc_seconds"), int | float)
    ]
    scores = [
        float(event["risk_score"])
        for event in events
        if isinstance(event.get("risk_score"), int | float)
    ]

    vehicles = sum(
        1 for event in events if event.get("event_type") != EventType.HAZARD_REPORT.value
    )

    inputs = RiskInputs(
        near_miss_count=breakdown.get(EventType.NEAR_MISS.value, 0),
        violation_count=sum(
            count
            for key, count in breakdown.items()
            if key and EVENT_CATEGORY.get(EventType(key)) is EventCategory.VIOLATION
        ),
        hard_braking_count=breakdown.get(EventType.HARD_BRAKING.value, 0),
        sudden_acceleration_count=breakdown.get(EventType.SUDDEN_ACCELERATION.value, 0),
        wrong_way_count=breakdown.get(EventType.WRONG_WAY.value, 0),
        pedestrian_conflict_count=breakdown.get(EventType.PEDESTRIAN_CONFLICT.value, 0),
        lane_change_count=breakdown.get(EventType.DANGEROUS_LANE_CHANGE.value, 0),
        vehicle_count=vehicles,
        observation_hours=float(window_hours),
        minimum_ttc_s=min(ttcs) if ttcs else None,
        mean_interaction_score=(sum(scores) / len(scores)) if scores else None,
        confirmed_hazard_count=sum(
            1
            for event in events
            if event.get("event_type") == EventType.HAZARD_REPORT.value
            and event.get("review_status") == "CONFIRMED"
        ),
    )
    return inputs, dict(breakdown)


def _peak_hour(events: list[dict[str, Any]]) -> int | None:
    hours = Counter(
        timestamp.hour
        for event in events
        if isinstance(timestamp := event.get("timestamp"), datetime)
    )
    return hours.most_common(1)[0][0] if hours else None


def _latest_timestamp(events: list[dict[str, Any]]) -> datetime | None:
    stamps = [
        event["timestamp"] for event in events if isinstance(event.get("timestamp"), datetime)
    ]
    return max(stamps) if stamps else None


def _event_centroid(events: list[dict[str, Any]]) -> LatLon | None:
    """Centre of the located events, weighted by risk.

    Weighted so the zone sits where the serious conflicts actually happened,
    not at the arithmetic middle of everything including the minor events.
    """
    total_weight = 0.0
    lat_sum = 0.0
    lon_sum = 0.0

    for event in events:
        location = event.get("location")
        if not isinstance(location, dict):
            continue
        score = event.get("risk_score")
        weight = float(score) if isinstance(score, int | float) and score > 0 else 10.0
        lat_sum += float(location["latitude"]) * weight
        lon_sum += float(location["longitude"]) * weight
        total_weight += weight

    if total_weight <= 0:
        return None
    return LatLon(lat_sum / total_weight, lon_sum / total_weight)


def _segment_midpoint(document: dict[str, Any]) -> LatLon | None:
    points = [
        LatLon(float(p["latitude"]), float(p["longitude"]))
        for p in document.get("path", [])
        if isinstance(p, dict)
    ]
    if not points:
        return None
    return points[len(points) // 2]


def risk_level_name(score: float) -> str:
    return risk_level_from_score(score).value
