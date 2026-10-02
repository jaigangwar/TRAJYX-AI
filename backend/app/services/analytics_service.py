"""Analytics aggregation.

One read of the event collection inside the window feeds every breakdown, so
the page costs a single query rather than one per chart. The window is bounded
by `since`, keeping the cost proportional to recent activity rather than to the
whole collection.

The rules this module holds to:

* A bucket that saw no scored event reports `mean_risk: null`, never 0.
* A breakdown nothing has produced is `available: false` with the reason,
  never an empty chart implying a measured zero.
* Rates are only reported when both numerator and denominator were measured.
  Helmet compliance has a known numerator and an unknown denominator, so the
  count is reported and the rate is not.
"""

from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

import structlog
from trajyx_shared.domain import (
    EVENT_CATEGORY,
    DataOrigin,
    EventCategory,
    EventType,
    RiskLevel,
    Severity,
    risk_level_from_score,
)

from app.repositories.base import DocumentStore, Filter, Query, utc_now
from app.schemas.analytics import (
    AnalyticsResponse,
    AnalyticsTotals,
    Breakdown,
    Bucket,
    CoverageRow,
    SegmentRow,
    Slice,
)
from app.schemas.dashboard import Metric

log = structlog.get_logger(__name__)

EVENTS = "risk_events"
ANALYSES = "video_analysis"
SEGMENTS = "road_segments"

#: Human labels for the checks the CV pipeline can gate on camera geometry.
#: Keys match the `unavailable_checks` names the worker records.
CHECK_LABELS = {
    "speed": "Speed estimation",
    "overspeed": "Overspeed",
    "wrong_way_detection": "Wrong-way driving",
    "red_light_violation": "Red-light running",
    "stop_line_violation": "Stop-line violation",
    "helmet_detection": "Helmet compliance",
    "seatbelt_detection": "Seatbelt compliance",
    "triple_riding": "Triple riding",
    "time_to_collision": "Time-to-collision",
}

MAX_DAY_BUCKETS = 90


def _label(value: str) -> str:
    """Turn an enum value into a display label."""
    return value.replace("_", " ").capitalize()


def _share(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _breakdown(counts: Counter[str], reason: str, labels: dict[str, str] | None = None) -> Breakdown:
    """Build a breakdown, or mark it unavailable when nothing was counted."""
    total = sum(counts.values())
    if total == 0:
        return Breakdown(slices=[], total=0, available=False, unavailable_reason=reason)
    return Breakdown(
        slices=[
            Slice(
                key=key,
                label=(labels or {}).get(key, _label(key)),
                count=count,
                share=_share(count, total),
            )
            for key, count in counts.most_common()
        ],
        total=total,
        available=True,
    )


class _Accumulator:
    """Running counts for one time bucket."""

    __slots__ = ("events", "near_misses", "violations", "risk_total", "scored")

    def __init__(self) -> None:
        self.events = 0
        self.near_misses = 0
        self.violations = 0
        self.risk_total = 0.0
        self.scored = 0

    def add(self, *, near_miss: bool, violation: bool, score: float | None) -> None:
        self.events += 1
        if near_miss:
            self.near_misses += 1
        if violation:
            self.violations += 1
        if score is not None:
            self.risk_total += score
            self.scored += 1

    def bucket(self, key: str, label: str) -> Bucket:
        return Bucket(
            key=key,
            label=label,
            events=self.events,
            near_misses=self.near_misses,
            violations=self.violations,
            # Null, not zero: no scored event means no measured mean.
            mean_risk=round(self.risk_total / self.scored, 1) if self.scored else None,
            scored_events=self.scored,
        )


def window_label(hours: float) -> str:
    """The window in the largest sensible unit, for display."""
    if hours < 48:
        return f"{hours:.0f}h"
    return f"{hours / 24:.0f} days"


class AnalyticsService:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    async def compute(self, window_hours: int, *, demo_mode: bool) -> AnalyticsResponse:
        now = utc_now()
        since = now - timedelta(hours=window_hours)

        events = await self._events_since(since)
        analyses = await self._analyses_since(since)

        by_hour = [_Accumulator() for _ in range(24)]
        by_weekday = [_Accumulator() for _ in range(7)]
        by_day: dict[str, _Accumulator] = defaultdict(_Accumulator)

        type_counts: Counter[str] = Counter()
        category_counts: Counter[str] = Counter()
        severity_counts: Counter[str] = Counter()
        origin_counts: Counter[str] = Counter()
        segment_events: dict[str, _Accumulator] = defaultdict(_Accumulator)

        critical = 0
        scored = 0
        risk_total = 0.0

        for document in events:
            timestamp = document.get("timestamp")
            if not isinstance(timestamp, datetime):
                continue

            raw_type = str(document.get("event_type", ""))
            try:
                event_type = EventType(raw_type)
            except ValueError:
                # An event type this build does not know about. Counting it
                # under a made-up label would be worse than skipping it.
                log.warning("analytics.unknown_event_type", event_type=raw_type)
                continue

            category = EVENT_CATEGORY[event_type]
            raw_score = document.get("risk_score")
            score = float(raw_score) if isinstance(raw_score, int | float) else None

            near_miss = event_type is EventType.NEAR_MISS
            violation = category is EventCategory.VIOLATION

            by_hour[timestamp.hour].add(near_miss=near_miss, violation=violation, score=score)
            by_weekday[timestamp.weekday()].add(
                near_miss=near_miss, violation=violation, score=score
            )
            by_day[timestamp.date().isoformat()].add(
                near_miss=near_miss, violation=violation, score=score
            )

            segment_id = document.get("road_segment_id")
            if isinstance(segment_id, str) and segment_id:
                segment_events[segment_id].add(
                    near_miss=near_miss, violation=violation, score=score
                )

            type_counts[event_type.value] += 1
            category_counts[category.value] += 1
            origin_counts[str(document.get("origin", DataOrigin.MEASURED.value))] += 1

            raw_severity = str(document.get("severity", ""))
            if raw_severity in {member.value for member in Severity}:
                severity_counts[raw_severity] += 1

            if score is not None:
                scored += 1
                risk_total += score
                if risk_level_from_score(score) is RiskLevel.CRITICAL:
                    critical += 1

        totals = AnalyticsTotals(
            events=len(events),
            violations=category_counts[EventCategory.VIOLATION.value],
            behaviour=category_counts[EventCategory.BEHAVIOR.value],
            interactions=category_counts[EventCategory.INTERACTION.value],
            reports=category_counts[EventCategory.REPORT.value],
            near_misses=type_counts[EventType.NEAR_MISS.value],
            critical=critical,
            scored_events=scored,
            mean_risk=(
                Metric.measured(round(risk_total / scored, 1))
                if scored
                else Metric.unavailable(
                    "No event in this window carried a risk score. Scores come from the "
                    "analysis pipeline and the geospatial aggregator."
                )
            ),
            demo_events=origin_counts[DataOrigin.DEMO.value],
        )

        empty_reason = (
            f"No events are stored in the last {window_label(window_hours)}. "
            "Analyse footage or widen the window."
        )

        return AnalyticsResponse(
            generated_at=now,
            window_hours=window_hours,
            window_label=window_label(window_hours),
            demo_mode=demo_mode,
            totals=totals,
            by_hour=[
                accumulator.bucket(f"{hour:02d}", f"{hour:02d}:00")
                for hour, accumulator in enumerate(by_hour)
            ],
            by_weekday=[
                accumulator.bucket(str(index), calendar.day_abbr[index])
                for index, accumulator in enumerate(by_weekday)
            ],
            by_day=self._day_series(by_day, since, now),
            by_event_type=_breakdown(type_counts, empty_reason),
            by_category=_breakdown(category_counts, empty_reason),
            by_severity=_breakdown(severity_counts, empty_reason),
            by_origin=_breakdown(origin_counts, empty_reason),
            traffic_composition=self._composition(analyses),
            peak_hour=self._peak_hour(by_hour),
            peak_hour_events=self._peak_hour_events(by_hour),
            helmet_violations=Metric.measured(
                float(type_counts[EventType.HELMET_VIOLATION.value])
            ),
            helmet_compliance_rate=self._helmet_rate(analyses),
            mean_inference_ms=self._inference_latency(analyses),
            detector_coverage=self._coverage(analyses),
            top_segments=await self._top_segments(segment_events),
        )

    # ----------------------------------------------------------------- reads

    async def _events_since(self, since: datetime) -> list[dict[str, Any]]:
        page = await self._store.query(
            EVENTS,
            Query().where(Filter.gte("timestamp", since)).order_by("timestamp", descending=True),
        )
        return list(page.documents)

    async def _analyses_since(self, since: datetime) -> list[dict[str, Any]]:
        page = await self._store.query(ANALYSES)
        return [
            document
            for document in page.documents
            if isinstance(document.get("created_at"), datetime)
            and document["created_at"] >= since
        ]

    # ------------------------------------------------------------ derivations

    def _day_series(
        self, buckets: dict[str, _Accumulator], since: datetime, now: datetime
    ) -> list[Bucket]:
        """One bucket per day in the window, including days with no activity.

        Gaps are filled so a flat stretch reads as a flat line rather than as
        two adjacent points joined across a week. Very long windows are capped
        so a 30-day request cannot turn into an unreadable axis.
        """
        span_days = max(1, (now.date() - since.date()).days + 1)
        if span_days > MAX_DAY_BUCKETS:
            # Beyond the cap, show only the days that actually have data.
            return [
                buckets[key].bucket(key, key)
                for key in sorted(buckets)
            ]

        series: list[Bucket] = []
        for offset in range(span_days):
            day = (since + timedelta(days=offset)).date()
            key = day.isoformat()
            accumulator = buckets.get(key, _Accumulator())
            series.append(accumulator.bucket(key, day.strftime("%d %b")))
        return series

    def _composition(self, analyses: list[dict[str, Any]]) -> Breakdown:
        """Traffic composition by vehicle class, summed over analysis runs.

        The empty case has two distinct causes and they are reported
        differently: no run at all, versus runs that completed and detected
        nothing. Collapsing them would tell an operator their cameras have not
        been analysed when in fact the detector found no vehicles — a very
        different thing to go and investigate.
        """
        counts: Counter[str] = Counter()
        for analysis in analyses:
            class_counts = analysis.get("class_counts")
            if isinstance(class_counts, dict):
                for label, value in class_counts.items():
                    if isinstance(value, int | float):
                        counts[str(label)] += int(value)

        if analyses:
            frames = sum(int(run.get("frames_analysed", 0) or 0) for run in analyses)
            reason = (
                f"{len(analyses)} analysis run(s) covering {frames} frames completed in this "
                "window, and the detector classified no vehicles in any of them. Composition is "
                "measured from detections, never inferred from event counts."
            )
        else:
            reason = (
                "No video has been analysed in this window, so no vehicle classes have been "
                "counted. Composition is measured from detections, never inferred from event "
                "counts."
            )

        return _breakdown(counts, reason)

    def _peak_hour(self, by_hour: list[_Accumulator]) -> Metric:
        busiest = max(range(24), key=lambda hour: by_hour[hour].events)
        if by_hour[busiest].events == 0:
            return Metric.unavailable("No events in this window, so there is no peak hour.")
        return Metric.measured(float(busiest), unit="hour")

    def _peak_hour_events(self, by_hour: list[_Accumulator]) -> Metric:
        peak = max(accumulator.events for accumulator in by_hour)
        if peak == 0:
            return Metric.unavailable("No events in this window.")
        return Metric.measured(float(peak), unit="events")

    def _helmet_rate(self, analyses: list[dict[str, Any]]) -> Metric:
        """Helmet compliance as a rate — which the platform cannot measure.

        The violation *count* is known. The rate needs a rider population, and
        nothing in the pipeline counts riders: helmet classification is gated
        off on every camera. Reporting `violations / detections` here would
        look like a compliance rate and would not be one.
        """
        reasons = {
            str(entry.get("reason"))
            for analysis in analyses
            for entry in analysis.get("unavailable_checks", [])
            if isinstance(entry, dict) and entry.get("name") == "helmet_detection"
        }
        detail = f" Pipeline reports: {sorted(reasons)[0]}" if reasons else ""
        return Metric.unavailable(
            "A compliance rate needs a rider count, and no deployed model classifies "
            "riders, so the denominator is unknown." + detail,
            unit="%",
        )

    def _inference_latency(self, analyses: list[dict[str, Any]]) -> Metric:
        """Mean measured inference time per frame across the window's runs."""
        samples = [
            float(analysis["inference_ms_per_frame"])
            for analysis in analyses
            if isinstance(analysis.get("inference_ms_per_frame"), int | float)
        ]
        if not samples:
            return Metric.unavailable(
                "No analysis run in this window recorded an inference time.", unit="ms"
            )
        return Metric.measured(round(sum(samples) / len(samples), 1), unit="ms")

    def _coverage(self, analyses: list[dict[str, Any]]) -> list[CoverageRow]:
        """Which safety checks could run, across the window's analysis runs."""
        if not analyses:
            return []

        unavailable: dict[str, Counter[str]] = defaultdict(Counter)
        for analysis in analyses:
            for entry in analysis.get("unavailable_checks", []):
                if isinstance(entry, dict) and entry.get("name"):
                    unavailable[str(entry["name"])][str(entry.get("reason", "Not stated."))] += 1

        total = len(analyses)
        rows = [
            CoverageRow(
                check=check,
                label=CHECK_LABELS.get(check, _label(check)),
                analyses_supported=total - sum(reasons.values()),
                analyses_total=total,
                reasons=[reason for reason, _ in reasons.most_common(3)],
            )
            for check, reasons in unavailable.items()
        ]
        # Checks nothing reported as unavailable ran everywhere.
        for check, label in CHECK_LABELS.items():
            if check not in unavailable:
                rows.append(
                    CoverageRow(
                        check=check, label=label, analyses_supported=total, analyses_total=total
                    )
                )
        rows.sort(key=lambda row: (row.analyses_supported, row.label))
        return rows

    async def _top_segments(self, activity: dict[str, _Accumulator]) -> list[SegmentRow]:
        """Road segments ranked by stored risk score.

        Event counts come from the window; the score comes from the segment
        record, which the geospatial aggregator wrote over its own window. The
        two are reported side by side rather than merged, so neither is
        presented as something it is not.
        """
        page = await self._store.query(SEGMENTS)
        rows: list[SegmentRow] = []
        for document in page.documents:
            segment_id = str(document.get("id", ""))
            accumulator = activity.get(segment_id, _Accumulator())
            raw_score = document.get("risk_score")
            score = float(raw_score) if isinstance(raw_score, int | float) else None
            if score is None and accumulator.events == 0:
                continue

            raw_hour = document.get("peak_hour")
            rows.append(
                SegmentRow(
                    id=segment_id,
                    name=str(document.get("name", "Unnamed segment")),
                    road_name=(
                        str(document["road_name"]) if document.get("road_name") else None
                    ),
                    risk_score=score,
                    # Banded from the score rather than read from the document.
                    # The aggregator deliberately does not store the level, so
                    # a stored copy can never disagree with the score it came
                    # from — the same rule `EventResponse.from_document` follows.
                    risk_level=(risk_level_from_score(score).value if score is not None else None),
                    events=accumulator.events,
                    near_misses=accumulator.near_misses,
                    violations=accumulator.violations,
                    peak_hour=int(raw_hour) if isinstance(raw_hour, int | float) else None,
                )
            )

        rows.sort(key=lambda row: (row.risk_score is None, -(row.risk_score or 0), -row.events))
        return rows[:12]
