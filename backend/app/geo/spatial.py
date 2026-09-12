"""Geospatial primitives.

Written over plain coordinates rather than a GIS library so the whole stack
runs without PostGIS. These are exactly the functions PostGIS would replace
with ``ST_DWithin`` and friends, which is what keeps that migration a swap
rather than a rewrite.

Distances use the haversine formula on a spherical Earth. At the scale that
matters here — a driver a few hundred metres from a junction — the error
against a proper ellipsoid is well under a metre, far below GPS accuracy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Mean Earth radius in metres (IUGG).
EARTH_RADIUS_M = 6_371_008.8


@dataclass(frozen=True, slots=True)
class LatLon:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not -90.0 <= self.latitude <= 90.0:
            raise ValueError(f"latitude out of range: {self.latitude}")
        if not -180.0 <= self.longitude <= 180.0:
            raise ValueError(f"longitude out of range: {self.longitude}")


def haversine_m(a: LatLon, b: LatLon) -> float:
    """Great-circle distance in metres."""
    lat1, lon1 = math.radians(a.latitude), math.radians(a.longitude)
    lat2, lon2 = math.radians(b.latitude), math.radians(b.longitude)

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def bearing_deg(origin: LatLon, destination: LatLon) -> float:
    """Initial great-circle bearing, degrees clockwise from true north.

    The same convention the CV pipeline uses for image-space headings, which
    is what lets one comparison function serve both.
    """
    lat1, lat2 = math.radians(origin.latitude), math.radians(destination.latitude)
    dlon = math.radians(destination.longitude - origin.longitude)

    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    if abs(x) < 1e-12 and abs(y) < 1e-12:
        return 0.0
    return math.degrees(math.atan2(y, x)) % 360.0


def angular_difference(first_deg: float, second_deg: float) -> float:
    """Smallest absolute angle between two bearings, in ``[0, 180]``."""
    delta = abs(first_deg - second_deg) % 360.0
    return delta if delta <= 180.0 else 360.0 - delta


def destination_point(origin: LatLon, bearing: float, distance_m: float) -> LatLon:
    """The point `distance_m` from `origin` along `bearing`."""
    angular = distance_m / EARTH_RADIUS_M
    lat1 = math.radians(origin.latitude)
    lon1 = math.radians(origin.longitude)
    theta = math.radians(bearing)

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular) + math.cos(lat1) * math.sin(angular) * math.cos(theta)
    )
    lon2 = lon1 + math.atan2(
        math.sin(theta) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    return LatLon(math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180)


@dataclass(frozen=True, slots=True)
class Projection:
    """Result of projecting a point onto a segment."""

    distance_m: float
    """Perpendicular distance from the point to the segment."""

    fraction: float
    """How far along the segment the closest point lies, 0-1."""

    closest: LatLon


def project_onto_segment(point: LatLon, start: LatLon, end: LatLon) -> Projection:
    """Project a point onto a line segment.

    Uses a local equirectangular approximation: longitude is scaled by
    cos(latitude) so that one unit of x and one unit of y are the same ground
    distance. Over a road segment of a few hundred metres this is accurate to
    centimetres, and it makes the projection ordinary 2-D vector algebra.
    """
    lat_reference = math.radians((start.latitude + end.latitude) / 2.0)
    scale = math.cos(lat_reference)

    def to_xy(item: LatLon) -> tuple[float, float]:
        return (item.longitude * scale, item.latitude)

    px, py = to_xy(point)
    ax, ay = to_xy(start)
    bx, by = to_xy(end)

    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy

    if length_squared < 1e-18:
        # Degenerate segment: treat it as a point.
        return Projection(distance_m=haversine_m(point, start), fraction=0.0, closest=start)

    raw = ((px - ax) * dx + (py - ay) * dy) / length_squared
    fraction = max(0.0, min(1.0, raw))

    closest = LatLon(
        latitude=ay + fraction * dy,
        longitude=(ax + fraction * dx) / scale if scale != 0 else point.longitude,
    )
    return Projection(
        distance_m=haversine_m(point, closest), fraction=fraction, closest=closest
    )


@dataclass(frozen=True, slots=True)
class BoundingBox:
    min_latitude: float
    min_longitude: float
    max_latitude: float
    max_longitude: float

    def contains(self, point: LatLon) -> bool:
        return (
            self.min_latitude <= point.latitude <= self.max_latitude
            and self.min_longitude <= point.longitude <= self.max_longitude
        )


def bounding_box_around(centre: LatLon, radius_m: float) -> BoundingBox:
    """A lat/lon box enclosing a radius.

    Used as a cheap pre-filter before computing exact distances: a bounding-box
    test is a comparison, a haversine is several trig calls, and the driver app
    runs this against every risk zone on every position update.
    """
    lat_delta = math.degrees(radius_m / EARTH_RADIUS_M)
    cos_lat = max(1e-6, math.cos(math.radians(centre.latitude)))
    lon_delta = math.degrees(radius_m / (EARTH_RADIUS_M * cos_lat))

    return BoundingBox(
        min_latitude=max(-90.0, centre.latitude - lat_delta),
        min_longitude=max(-180.0, centre.longitude - lon_delta),
        max_latitude=min(90.0, centre.latitude + lat_delta),
        max_longitude=min(180.0, centre.longitude + lon_delta),
    )


def is_ahead(
    position: LatLon, heading_deg: float, target: LatLon, tolerance_deg: float = 60.0
) -> bool:
    """Whether `target` lies ahead of a driver travelling on `heading_deg`.

    This is the check that stops the driver app warning about a hazard the
    driver has already passed, or one on a parallel road going the other way.
    Without it the alerts are noise and get ignored, which makes the whole
    product worse than useless.
    """
    target_bearing = bearing_deg(position, target)
    return angular_difference(heading_deg, target_bearing) <= tolerance_deg


def polyline_length_m(points: list[LatLon]) -> float:
    return sum(haversine_m(points[i], points[i + 1]) for i in range(len(points) - 1))


def polyline_bearing(points: list[LatLon]) -> float | None:
    """Overall direction of a polyline, from first point to last."""
    if len(points) < 2:
        return None
    return bearing_deg(points[0], points[-1])


def distance_to_polyline(point: LatLon, points: list[LatLon]) -> Projection | None:
    """Closest approach to a polyline, across all its segments."""
    if not points:
        return None
    if len(points) == 1:
        return Projection(haversine_m(point, points[0]), 0.0, points[0])

    best: Projection | None = None
    for index in range(len(points) - 1):
        projection = project_onto_segment(point, points[index], points[index + 1])
        if best is None or projection.distance_m < best.distance_m:
            best = projection
    return best
