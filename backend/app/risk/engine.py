"""Explainable risk scoring.

The score is a weighted sum of named, bounded factors. That is a deliberate
choice over a black box: an operator has to be able to answer "why is this
junction 88?" and a driver has to be told *what* to watch for, not just that
something is risky. A model that cannot explain itself cannot be acted on.

The ML model in phase 9 refines the weights; it does not replace the structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trajyx_shared.domain import RiskLevel, Severity, risk_level_from_score


@dataclass(frozen=True, slots=True)
class RiskFactor:
    """One named contribution to a risk score."""

    name: str
    """Human-readable, shown verbatim in the dashboard and the driver app."""

    value: float
    """Normalised 0-1 magnitude of the underlying observation."""

    weight: float
    """How much this factor can contribute, in score points."""

    detail: str | None = None

    @property
    def contribution(self) -> float:
        return round(self.value * self.weight, 2)


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    score: float
    level: RiskLevel
    factors: tuple[RiskFactor, ...]
    confidence: float
    """How much evidence backs this score, 0-1. Low when there is little data."""

    @property
    def top_factors(self) -> tuple[RiskFactor, ...]:
        """The three largest contributors, for a compact explanation."""
        return tuple(sorted(self.factors, key=lambda f: -f.contribution)[:3])

    def explain(self) -> list[str]:
        return [
            f"{factor.name}" + (f" — {factor.detail}" if factor.detail else "")
            for factor in self.top_factors
            if factor.contribution > 0.5
        ]


@dataclass(slots=True)
class RiskInputs:
    """Observations for one road segment (or one camera) over a window.

    Every field is a count or a measurement the pipeline actually produced.
    Nothing here is inferred from a constant.
    """

    near_miss_count: int = 0
    critical_near_miss_count: int = 0
    violation_count: int = 0
    critical_violation_count: int = 0
    hard_braking_count: int = 0
    sudden_acceleration_count: int = 0
    wrong_way_count: int = 0
    pedestrian_conflict_count: int = 0
    lane_change_count: int = 0

    vehicle_count: int = 0
    pedestrian_count: int = 0
    observation_hours: float = 1.0

    #: Minimum estimated TTC observed. None when no conflict was measured.
    minimum_ttc_s: float | None = None
    #: Mean interaction score across analysed pairs.
    mean_interaction_score: float | None = None

    #: Confirmed driver hazard reports on this segment.
    confirmed_hazard_count: int = 0

    #: Historical near misses, used to carry forward known danger.
    historical_near_miss_count: int = 0

    hour_of_day: int | None = None

    #: Shortest window treated as representative. A 12-second clip with two
    #: near misses is not "600 near misses an hour"; extrapolating from that
    #: little evidence produces a confident-looking number built on nothing.
    MINIMUM_WINDOW_HOURS = 0.25

    def per_hour(self, count: int) -> float:
        return count / max(self.MINIMUM_WINDOW_HOURS, self.observation_hours)

    @property
    def window_label(self) -> str:
        """The observation window in the largest sensible unit.

        Shown verbatim to operators and drivers, so "168 in 14 days" rather
        than "168 in 336.0h".
        """
        if self.observation_hours < 1 / 60:
            return f"{self.observation_hours * 3600:.0f}s"
        if self.observation_hours < 1:
            return f"{self.observation_hours * 60:.0f} min"
        if self.observation_hours < 48:
            return f"{self.observation_hours:.0f}h"
        return f"{self.observation_hours / 24:.0f} days"


# Weights sum to 100. Ordered by how predictive each signal is of an actual
# collision, per the road-safety literature: conflicts (near misses) are the
# strongest leading indicator, then wrong-way and pedestrian exposure, with
# raw traffic volume a comparatively weak signal on its own.
WEIGHTS = {
    "near_miss": 26.0,
    "ttc": 18.0,
    "wrong_way": 12.0,
    "pedestrian": 10.0,
    "violation": 10.0,
    "braking": 8.0,
    "interaction": 7.0,
    "density": 5.0,
    "history": 4.0,
}

#: Hours when risk is elevated independently of observed counts: dusk and the
#: evening peak. Applied as a small multiplier, not a score of its own, so it
#: can never manufacture risk on an empty road.
ELEVATED_HOURS = {17, 18, 19, 20, 21}
TIME_OF_DAY_MULTIPLIER = 1.08


# Saturation references, as events per hour.
#
# These are calibrated against realistic observed rates, which matters more
# than it looks: an earlier version used 4 near misses *per hour* as the
# saturation point. A genuinely dangerous urban junction produces a handful
# per *day* — roughly 0.2-0.5 per hour — so every real road scored LOW and the
# system generated no risk zones at all and therefore never warned anybody.
#
# A rate at or above the reference contributes the factor's full weight.
REFERENCES = {
    #: ~12 near misses a day is a seriously conflict-prone junction.
    "near_miss_per_hour": 0.5,
    #: Wrong-way travel is rare and severe; 2-3 a day is alarming.
    "wrong_way_per_hour": 0.1,
    #: Pedestrian conflicts: ~7 a day on a bad crossing.
    "pedestrian_conflict_per_hour": 0.3,
    #: Violations are common, so the bar is higher: ~36 a day.
    "violation_per_hour": 1.5,
    #: Abrupt braking and acceleration: ~72 a day marks a disrupted flow.
    "braking_per_hour": 3.0,
    #: Traffic volume, for the density factor.
    "vehicles_per_hour": 400.0,
    #: Historical weight, as a raw count rather than a rate.
    "history_count": 20.0,
}


def _saturating(value: float, reference: float) -> float:
    """Map a rate onto 0-1, saturating at `reference`.

    Saturating rather than linear because the difference between 10 and 20 near
    misses an hour is not as meaningful as the difference between 0 and 5 —
    both of the former are already "this place is dangerous".
    """
    if reference <= 0:
        return 0.0
    return min(1.0, max(0.0, value / reference))


def assess(inputs: RiskInputs, now: datetime | None = None) -> RiskAssessment:
    """Score a road segment or camera from observed events."""
    factors: list[RiskFactor] = []

    near_miss_rate = inputs.per_hour(inputs.near_miss_count)
    factors.append(
        RiskFactor(
            name="Recent near misses",
            value=_saturating(near_miss_rate, REFERENCES["near_miss_per_hour"]),
            weight=WEIGHTS["near_miss"],
            detail=f"{inputs.near_miss_count} in {inputs.window_label}"
            if inputs.near_miss_count
            else None,
        )
    )

    if inputs.minimum_ttc_s is not None:
        # 0 s -> 1.0, 5 s or more -> 0.
        urgency = max(0.0, 1.0 - inputs.minimum_ttc_s / 5.0)
        factors.append(
            RiskFactor(
                name="Short time to collision",
                value=urgency,
                weight=WEIGHTS["ttc"],
                detail=f"estimated minimum {inputs.minimum_ttc_s:.1f}s",
            )
        )
    else:
        factors.append(RiskFactor("Short time to collision", 0.0, WEIGHTS["ttc"]))

    factors.append(
        RiskFactor(
            name="Wrong-way movement",
            value=_saturating(inputs.per_hour(inputs.wrong_way_count), REFERENCES["wrong_way_per_hour"]),
            weight=WEIGHTS["wrong_way"],
            detail=f"{inputs.wrong_way_count} vehicles" if inputs.wrong_way_count else None,
        )
    )

    pedestrian_exposure = 0.0
    if inputs.vehicle_count > 0 and inputs.pedestrian_count > 0:
        # Exposure is the product of both populations, not either alone: a
        # pedestrian on an empty road is not at risk, and neither is heavy
        # traffic with nobody crossing.
        share = inputs.pedestrian_count / max(1, inputs.vehicle_count + inputs.pedestrian_count)
        pedestrian_exposure = _saturating(share * 4.0, 1.0)
    factors.append(
        RiskFactor(
            name="Pedestrian exposure",
            value=max(
                pedestrian_exposure,
                _saturating(
                    inputs.per_hour(inputs.pedestrian_conflict_count),
                    REFERENCES["pedestrian_conflict_per_hour"],
                ),
            ),
            weight=WEIGHTS["pedestrian"],
            detail=f"{inputs.pedestrian_conflict_count} conflicts"
            if inputs.pedestrian_conflict_count
            else (f"{inputs.pedestrian_count} pedestrians" if inputs.pedestrian_count else None),
        )
    )

    factors.append(
        RiskFactor(
            name="Traffic violations",
            value=_saturating(inputs.per_hour(inputs.violation_count), REFERENCES["violation_per_hour"]),
            weight=WEIGHTS["violation"],
            detail=f"{inputs.violation_count} recorded" if inputs.violation_count else None,
        )
    )

    braking_rate = inputs.per_hour(inputs.hard_braking_count + inputs.sudden_acceleration_count)
    factors.append(
        RiskFactor(
            name="Abrupt braking and acceleration",
            value=_saturating(braking_rate, REFERENCES["braking_per_hour"]),
            weight=WEIGHTS["braking"],
            detail=f"{inputs.hard_braking_count} hard brakes"
            if inputs.hard_braking_count
            else None,
        )
    )

    factors.append(
        RiskFactor(
            name="Vehicle conflict intensity",
            value=(inputs.mean_interaction_score or 0.0) / 100.0,
            weight=WEIGHTS["interaction"],
            detail=f"mean interaction score {inputs.mean_interaction_score:.0f}"
            if inputs.mean_interaction_score
            else None,
        )
    )

    factors.append(
        RiskFactor(
            name="Traffic density",
            value=_saturating(inputs.per_hour(inputs.vehicle_count), REFERENCES["vehicles_per_hour"]),
            weight=WEIGHTS["density"],
            detail=f"{inputs.vehicle_count} vehicles" if inputs.vehicle_count else None,
        )
    )

    factors.append(
        RiskFactor(
            name="Historical incidents",
            value=_saturating(
                float(inputs.historical_near_miss_count + inputs.confirmed_hazard_count * 2),
                REFERENCES["history_count"],
            ),
            weight=WEIGHTS["history"],
            detail=f"{inputs.confirmed_hazard_count} confirmed hazards"
            if inputs.confirmed_hazard_count
            else None,
        )
    )

    score = sum(factor.contribution for factor in factors)

    hour = inputs.hour_of_day if inputs.hour_of_day is not None else (now.hour if now else None)
    if hour in ELEVATED_HOURS and score > 0:
        # Multiplier, not an additive factor: it can amplify observed risk but
        # never invent risk where nothing was observed.
        score *= TIME_OF_DAY_MULTIPLIER
        factors.append(
            RiskFactor(
                name="Evening peak period",
                value=1.0,
                weight=0.0,
                detail=f"{hour:02d}:00 uplift applied",
            )
        )

    score = round(min(100.0, max(0.0, score)), 1)

    return RiskAssessment(
        score=score,
        level=risk_level_from_score(score),
        factors=tuple(factors),
        confidence=_confidence(inputs),
    )


def _confidence(inputs: RiskInputs) -> float:
    """How much evidence backs the score.

    A segment observed for four minutes with three vehicles should not be
    presented with the same certainty as one observed for a week. Reported
    alongside the score so a thin assessment is visibly thin.
    """
    observations = inputs.vehicle_count + inputs.pedestrian_count
    volume = _saturating(float(observations), 200.0)
    duration = _saturating(inputs.observation_hours, 4.0)
    events = _saturating(
        float(inputs.near_miss_count + inputs.violation_count + inputs.hard_braking_count), 10.0
    )
    return round(min(0.95, 0.15 + 0.4 * volume + 0.3 * duration + 0.15 * events), 2)


def severity_for(level: RiskLevel) -> Severity:
    return {
        RiskLevel.LOW: Severity.INFO,
        RiskLevel.MODERATE: Severity.MINOR,
        RiskLevel.HIGH: Severity.MAJOR,
        RiskLevel.CRITICAL: Severity.CRITICAL,
    }[level]


@dataclass(frozen=True, slots=True)
class HourlyRisk:
    hour: int
    score: float
    level: RiskLevel
    event_count: int


def risk_by_hour(
    events_by_hour: dict[int, RiskInputs], now: datetime | None = None
) -> list[HourlyRisk]:
    """Score each hour separately.

    Road risk is not a constant property of a place — the same junction is
    quiet at 06:00 and dangerous at 19:00. Scoring per hour is what makes the
    driver warning time-aware.
    """
    results: list[HourlyRisk] = []
    for hour in range(24):
        inputs = events_by_hour.get(hour)
        if inputs is None:
            continue
        inputs.hour_of_day = hour
        assessment = assess(inputs, now)
        results.append(
            HourlyRisk(
                hour=hour,
                score=assessment.score,
                level=assessment.level,
                event_count=inputs.near_miss_count
                + inputs.violation_count
                + inputs.hard_braking_count,
            )
        )
    return results


def assessment_to_dict(assessment: RiskAssessment) -> dict[str, object]:
    """Serialise for storage and API responses."""
    return {
        "risk_score": assessment.score,
        "risk_level": assessment.level.value,
        "confidence": assessment.confidence,
        "factors": [
            {
                "name": factor.name,
                "value": round(factor.value, 3),
                "weight": factor.weight,
                "contribution": factor.contribution,
                "detail": factor.detail,
            }
            for factor in assessment.factors
            if factor.contribution > 0 or factor.weight == 0
        ],
        "top_factors": assessment.explain(),
    }
