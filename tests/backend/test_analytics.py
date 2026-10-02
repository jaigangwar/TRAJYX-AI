"""Analytics aggregation, reporting and the model registry.

The assertions here are mostly about what the platform *refuses* to claim.
Three rules carry the file:

* A bucket with no scored event reports ``mean_risk: null``. An hour in which
  nothing was scored and an hour in which everything scored zero are different
  facts about a road, and a chart that draws 0 for both is lying.
* A rate is only reported when both numerator and denominator were measured.
  Helmet compliance has a known numerator and an unknown denominator, so the
  count is reported and the rate is refused.
* The model registry cannot name a model that never ran, cannot borrow one
  component's version or latency for another, and never reports accuracy
  without a recorded evaluation against a named dataset.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from tests.backend.conftest import auth_header
from trajyx_shared.domain import DataOrigin, EventType, ModelHealth, ReportStatus, Role, Severity

ANALYTICS = "/api/v1/analytics/summary"
REPORTS = "/api/v1/reports"
MODELS = "/api/v1/models/health"


def event_document(
    event_type: EventType,
    *,
    risk_score: float | None = None,
    origin: DataOrigin = DataOrigin.MEASURED,
    severity: Severity = Severity.INFO,
    hours_ago: float = 1,
    road_segment_id: str | None = None,
) -> dict:
    from trajyx_shared.domain import EVENT_CATEGORY

    return {
        "event_type": event_type.value,
        "category": EVENT_CATEGORY[event_type].value,
        "timestamp": datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        "camera_id": None,
        "road_segment_id": road_segment_id,
        "location": {"latitude": 28.61, "longitude": 77.20},
        "severity": severity.value,
        "confidence": 0.9,
        "risk_score": risk_score,
        "origin": origin.value,
        "model_version": "test-1.0",
        "track_ids": [1],
        "details": {},
        "review_status": ReportStatus.PENDING.value,
    }


async def seed_events(app, documents: list[dict]) -> None:
    await app.state.store.bulk_create("risk_events", documents)


async def seed_analysis(app, **overrides) -> None:
    """Write an analysis run the way the worker does."""
    document = {
        "job_id": "job-1",
        "camera_id": None,
        "frames_analysed": 150,
        "frame_stride": 2,
        "detector_name": "ultralytics-yolo",
        "detector_version": "yolov8n-1.0",
        "tracker_name": "bytetrack",
        "inference_ms_per_frame": 40.0,
        "detection_count": 120,
        "vehicle_count": 100,
        "pedestrian_count": 20,
        "class_counts": {"CAR": 80, "MOTORCYCLE": 20},
        "unavailable_checks": [
            {"name": "helmet_detection", "reason": "No rider classification model is deployed."}
        ],
        "origin": DataOrigin.MEASURED.value,
        "created_at": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    document.update(overrides)
    await app.state.store.create("video_analysis", document)


class TestAnalyticsHonesty:
    @pytest.mark.anyio
    async def test_an_hour_with_events_but_no_scores_reports_null_not_zero(
        self, client: TestClient, admin_token: str
    ) -> None:
        # Two events four hours ago, neither carrying a risk score.
        await seed_events(
            client.app,
            [event_document(EventType.HARD_BRAKING, hours_ago=4) for _ in range(2)],
        )

        body = client.get(ANALYTICS, headers=auth_header(admin_token)).json()
        target_hour = (datetime.now(timezone.utc) - timedelta(hours=4)).hour
        bucket = body["by_hour"][target_hour]

        assert bucket["events"] == 2, "the events themselves are counted"
        assert bucket["scored_events"] == 0
        assert bucket["mean_risk"] is None, "no scored event means no measured mean"

    @pytest.mark.anyio
    async def test_a_scored_hour_reports_its_measured_mean(
        self, client: TestClient, admin_token: str
    ) -> None:
        await seed_events(
            client.app,
            [
                event_document(EventType.NEAR_MISS, risk_score=80.0, hours_ago=3),
                event_document(EventType.NEAR_MISS, risk_score=60.0, hours_ago=3),
            ],
        )

        body = client.get(ANALYTICS, headers=auth_header(admin_token)).json()
        bucket = body["by_hour"][(datetime.now(timezone.utc) - timedelta(hours=3)).hour]

        assert bucket["scored_events"] == 2
        assert bucket["mean_risk"] == 70.0

    def test_helmet_compliance_rate_is_refused_with_a_reason(
        self, client: TestClient, admin_token: str
    ) -> None:
        body = client.get(ANALYTICS, headers=auth_header(admin_token)).json()

        rate = body["helmet_compliance_rate"]
        assert rate["available"] is False
        assert rate["value"] is None
        assert "denominator" in rate["unavailable_reason"]

        # The count, unlike the rate, is measurable and is reported.
        assert body["helmet_violations"]["available"] is True

    @pytest.mark.anyio
    async def test_helmet_violations_are_counted_while_the_rate_stays_refused(
        self, client: TestClient, admin_token: str
    ) -> None:
        await seed_events(
            client.app, [event_document(EventType.HELMET_VIOLATION) for _ in range(3)]
        )

        body = client.get(ANALYTICS, headers=auth_header(admin_token)).json()
        assert body["helmet_violations"]["value"] == 3.0
        assert body["helmet_compliance_rate"]["available"] is False

    def test_an_empty_window_refuses_breakdowns_rather_than_showing_empty_charts(
        self, client: TestClient, admin_token: str
    ) -> None:
        body = client.get(ANALYTICS, headers=auth_header(admin_token)).json()

        for key in ("by_event_type", "by_category", "by_severity", "traffic_composition"):
            breakdown = body[key]
            assert breakdown["available"] is False, key
            assert breakdown["slices"] == []
            assert breakdown["unavailable_reason"]

        assert body["peak_hour"]["available"] is False
        assert body["totals"]["mean_risk"]["available"] is False

    @pytest.mark.anyio
    async def test_composition_distinguishes_no_run_from_a_run_that_saw_nothing(
        self, client: TestClient, admin_token: str
    ) -> None:
        """The two empty cases are different problems to go and investigate."""
        no_run = client.get(ANALYTICS, headers=auth_header(admin_token)).json()
        assert "No video has been analysed" in no_run["traffic_composition"]["unavailable_reason"]

        await seed_analysis(client.app, class_counts={}, detection_count=0)

        after = client.get(ANALYTICS, headers=auth_header(admin_token)).json()
        reason = after["traffic_composition"]["unavailable_reason"]
        assert "classified no vehicles" in reason
        assert "150 frames" in reason, "the reason names what was actually looked at"

    @pytest.mark.anyio
    async def test_composition_is_measured_from_detections(
        self, client: TestClient, admin_token: str
    ) -> None:
        await seed_analysis(client.app)

        body = client.get(ANALYTICS, headers=auth_header(admin_token)).json()
        composition = body["traffic_composition"]

        assert composition["available"] is True
        assert composition["total"] == 100
        assert {s["key"]: s["count"] for s in composition["slices"]} == {
            "CAR": 80,
            "MOTORCYCLE": 20,
        }

    @pytest.mark.anyio
    async def test_the_synthetic_share_of_the_window_is_disclosed(
        self, client: TestClient, admin_token: str
    ) -> None:
        await seed_events(
            client.app,
            [
                event_document(EventType.HARD_BRAKING, origin=DataOrigin.MEASURED),
                event_document(EventType.HARD_BRAKING, origin=DataOrigin.DEMO),
                event_document(EventType.HARD_BRAKING, origin=DataOrigin.DEMO),
            ],
        )

        body = client.get(ANALYTICS, headers=auth_header(admin_token)).json()
        assert body["totals"]["events"] == 3
        assert body["totals"]["demo_events"] == 2

        origins = {s["key"]: s["count"] for s in body["by_origin"]["slices"]}
        assert origins == {"MEASURED": 1, "DEMO": 2}

    @pytest.mark.anyio
    async def test_detector_coverage_reports_what_a_camera_could_not_check(
        self, client: TestClient, admin_token: str
    ) -> None:
        await seed_analysis(client.app)

        body = client.get(ANALYTICS, headers=auth_header(admin_token)).json()
        rows = {row["check"]: row for row in body["detector_coverage"]}

        helmet = rows["helmet_detection"]
        assert helmet["analyses_supported"] == 0
        assert helmet["analyses_total"] == 1
        assert helmet["reasons"] == ["No rider classification model is deployed."]

        # A check nothing reported as unavailable ran on every analysis.
        assert rows["time_to_collision"]["analyses_supported"] == 1

    def test_buckets_are_always_complete_so_a_gap_is_visible(
        self, client: TestClient, admin_token: str
    ) -> None:
        body = client.get(ANALYTICS, headers=auth_header(admin_token)).json()
        assert len(body["by_hour"]) == 24
        assert len(body["by_weekday"]) == 7
        assert [b["key"] for b in body["by_weekday"]] == [str(i) for i in range(7)]

    def test_requires_authentication(self, client: TestClient) -> None:
        assert client.get(ANALYTICS).status_code == 401

    def test_a_driver_cannot_read_platform_analytics(
        self, client: TestClient, role_tokens: dict[Role, str]
    ) -> None:
        response = client.get(ANALYTICS, headers=auth_header(role_tokens[Role.DRIVER]))
        assert response.status_code == 403

    def test_an_analyst_can_read_analytics(
        self, client: TestClient, role_tokens: dict[Role, str]
    ) -> None:
        response = client.get(ANALYTICS, headers=auth_header(role_tokens[Role.ANALYST]))
        assert response.status_code == 200


class TestReports:
    def test_the_catalogue_lists_only_types_with_a_builder(
        self, client: TestClient, admin_token: str
    ) -> None:
        body = client.get(f"{REPORTS}/types", headers=auth_header(admin_token)).json()
        offered = {entry["type"] for entry in body}

        assert offered == {"DAILY", "WEEKLY", "ROAD_SAFETY", "VIOLATION", "HOTSPOT"}
        for entry in body:
            # Generating every offered type must succeed, or the catalogue is
            # advertising something the backend cannot build.
            response = client.post(
                REPORTS,
                headers=auth_header(admin_token),
                json={"type": entry["type"], "window_hours": 24},
            )
            assert response.status_code == 201, f"{entry['type']}: {response.text}"

    @pytest.mark.anyio
    async def test_a_report_records_its_parameters_and_synthetic_share(
        self, client: TestClient, admin_token: str
    ) -> None:
        await seed_events(
            client.app,
            [
                event_document(EventType.WRONG_WAY, origin=DataOrigin.DEMO, risk_score=90.0),
                event_document(EventType.OVERSPEED, origin=DataOrigin.MEASURED),
            ],
        )

        report = client.post(
            REPORTS,
            headers=auth_header(admin_token),
            json={"type": "DAILY", "window_hours": 24},
        ).json()

        assert report["record_count"] == 2
        assert report["demo_record_count"] == 1
        assert report["window_label"] == "24h"
        assert report["parameters"]["window_hours"] == 24
        assert report["generated_by"] == "admin@trajyx.test"
        assert "synthetic" in report["subtitle"]

    @pytest.mark.anyio
    async def test_a_stored_report_is_not_recomputed_when_reopened(
        self, client: TestClient, admin_token: str
    ) -> None:
        """A report is a record of what was true when it ran."""
        await seed_events(client.app, [event_document(EventType.HARD_BRAKING)])

        created = client.post(
            REPORTS, headers=auth_header(admin_token), json={"type": "DAILY", "window_hours": 24}
        ).json()
        assert created["record_count"] == 1

        # More events arrive after the report was issued.
        await seed_events(
            client.app, [event_document(EventType.HARD_BRAKING) for _ in range(5)]
        )

        reopened = client.get(
            f"{REPORTS}/{created['id']}", headers=auth_header(admin_token)
        ).json()
        assert reopened["record_count"] == 1, "the stored figure must not move"
        assert reopened["sections"] == created["sections"]

    def test_an_uncomputable_section_is_kept_and_marked(
        self, client: TestClient, admin_token: str
    ) -> None:
        report = client.post(
            REPORTS,
            headers=auth_header(admin_token),
            json={"type": "ROAD_SAFETY", "window_hours": 24},
        ).json()

        composition = next(
            section for section in report["sections"] if section["title"] == "Traffic composition"
        )
        # Dropped sections would leave a reader guessing whether "missing"
        # means "nothing happened" or "we cannot tell".
        assert composition["available"] is False
        assert composition["unavailable_reason"]

    @pytest.mark.anyio
    async def test_csv_export_carries_provenance_and_preserves_absent_values(
        self, client: TestClient, admin_token: str
    ) -> None:
        await seed_events(
            client.app,
            [event_document(EventType.HARD_BRAKING, origin=DataOrigin.DEMO, hours_ago=2)],
        )

        report = client.post(
            REPORTS, headers=auth_header(admin_token), json={"type": "DAILY", "window_hours": 24}
        ).json()

        response = client.get(
            f"{REPORTS}/{report['id']}/export?format=csv", headers=auth_header(admin_token)
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        assert "trajyx-daily-" in response.headers["content-disposition"]

        text = response.text
        assert "Generated by,admin@trajyx.test" in text
        assert "Synthetic records,1" in text
        assert "This report is not operational." in text

        rows = list(csv.reader(io.StringIO(text)))
        start = next(index for index, row in enumerate(rows) if row[:1] == ["# Activity by hour"])
        # The section title is followed by its note, also written as a comment
        # row, so the header is the first row that is not a comment.
        header_index = next(
            index
            for index in range(start + 1, len(rows))
            if rows[index] and not rows[index][0].startswith("#")
        )
        header = rows[header_index]
        first = rows[header_index + 1]
        mean_risk = first[header.index("Mean risk")]
        # The event carried no score, so the cell stays empty rather than
        # becoming a 0 that a spreadsheet would happily average.
        assert mean_risk == ""

    def test_json_export_is_the_stored_document(
        self, client: TestClient, admin_token: str
    ) -> None:
        report = client.post(
            REPORTS, headers=auth_header(admin_token), json={"type": "HOTSPOT", "window_hours": 24}
        ).json()

        response = client.get(
            f"{REPORTS}/{report['id']}/export?format=json", headers=auth_header(admin_token)
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["id"] == report["id"]

    def test_an_unknown_report_is_a_404(self, client: TestClient, admin_token: str) -> None:
        response = client.get(f"{REPORTS}/no-such-report", headers=auth_header(admin_token))
        assert response.status_code == 404

    def test_an_analyst_cannot_generate_a_report_but_can_read_one(
        self, client: TestClient, admin_token: str, role_tokens: dict[Role, str]
    ) -> None:
        analyst = auth_header(role_tokens[Role.ANALYST])
        assert (
            client.post(REPORTS, headers=analyst, json={"type": "DAILY", "window_hours": 24}).status_code
            == 403
        )
        assert client.get(REPORTS, headers=analyst).status_code == 200

    def test_a_driver_cannot_read_reports(
        self, client: TestClient, role_tokens: dict[Role, str]
    ) -> None:
        response = client.get(REPORTS, headers=auth_header(role_tokens[Role.DRIVER]))
        assert response.status_code == 403


class TestModelRegistry:
    def test_a_model_that_never_ran_is_not_listed(
        self, client: TestClient, admin_token: str
    ) -> None:
        body = client.get(MODELS, headers=auth_header(admin_token)).json()
        assert body["models"] == []
        assert body["evaluation_available"] is False

    @pytest.mark.anyio
    async def test_a_model_appears_because_a_run_used_it(
        self, client: TestClient, admin_token: str
    ) -> None:
        await seed_analysis(client.app)

        body = client.get(MODELS, headers=auth_header(admin_token)).json()
        by_role = {model["role"]: model for model in body["models"]}

        detector = by_role["detection"]
        assert detector["name"] == "ultralytics-yolo"
        assert detector["version"] == "yolov8n-1.0"
        assert detector["runs"] == 1
        assert detector["frames_processed"] == 150
        assert detector["registered"] is False, "observed, not registered"

    @pytest.mark.anyio
    async def test_the_tracker_does_not_borrow_the_detectors_version(
        self, client: TestClient, admin_token: str
    ) -> None:
        """A tracker labelled with the detector's version would attribute its
        runs to a build that never produced them."""
        await seed_analysis(client.app)

        body = client.get(MODELS, headers=auth_header(admin_token)).json()
        tracker = next(model for model in body["models"] if model["role"] == "tracking")

        assert tracker["name"] == "bytetrack"
        assert tracker["version"] is None
        assert any("no version" in note for note in tracker["notes"])

    @pytest.mark.anyio
    async def test_the_tracker_does_not_borrow_the_detectors_latency(
        self, client: TestClient, admin_token: str
    ) -> None:
        await seed_analysis(client.app, inference_ms_per_frame=40.0)

        body = client.get(MODELS, headers=auth_header(admin_token)).json()
        by_role = {model["role"]: model for model in body["models"]}

        assert by_role["detection"]["latency"]["mean_ms"]["value"] == 40.0

        tracker_latency = by_role["tracking"]["latency"]["mean_ms"]
        assert tracker_latency["available"] is False
        assert "times the detector, not the tracker" in tracker_latency["unavailable_reason"]
        # Speed unknown means health unknown, not health assumed good.
        assert by_role["tracking"]["health"] == ModelHealth.UNKNOWN.value

    @pytest.mark.anyio
    async def test_accuracy_is_refused_without_a_recorded_evaluation(
        self, client: TestClient, admin_token: str
    ) -> None:
        await seed_analysis(client.app)

        body = client.get(MODELS, headers=auth_header(admin_token)).json()
        accuracy = body["models"][0]["accuracy"]

        for field in ("precision", "recall", "f1"):
            assert accuracy[field]["available"] is False, field
            assert accuracy[field]["value"] is None
        assert "labelled evaluation set" in accuracy["precision"]["unavailable_reason"]
        assert "confidence is not a substitute" in accuracy["precision"]["unavailable_reason"]
        assert body["evaluation_available"] is False

    @pytest.mark.anyio
    async def test_a_registry_record_without_a_dataset_does_not_count_as_evaluated(
        self, client: TestClient, admin_token: str
    ) -> None:
        """A precision figure with no dataset behind it measures nothing."""
        await seed_analysis(client.app)
        await client.app.state.store.create(
            "model_versions",
            {"name": "ultralytics-yolo", "version": "yolov8n-1.0", "precision": 0.91},
        )

        body = client.get(MODELS, headers=auth_header(admin_token)).json()
        detector = next(model for model in body["models"] if model["role"] == "detection")

        assert detector["accuracy"]["precision"]["available"] is False
        assert detector["accuracy"]["dataset_version"] is None

    @pytest.mark.anyio
    async def test_a_real_evaluation_is_reported(
        self, client: TestClient, admin_token: str
    ) -> None:
        await seed_analysis(client.app)
        await client.app.state.store.create(
            "model_versions",
            {
                "name": "ultralytics-yolo",
                "version": "yolov8n-1.0",
                "dataset_version": "delhi-junctions-v3",
                "precision": 0.91,
                "recall": 0.87,
                "f1": 0.89,
                "evaluated_at": datetime.now(timezone.utc),
            },
        )

        body = client.get(MODELS, headers=auth_header(admin_token)).json()
        detector = next(model for model in body["models"] if model["role"] == "detection")

        assert detector["registered"] is True
        assert detector["accuracy"]["precision"]["value"] == 0.91
        assert detector["accuracy"]["dataset_version"] == "delhi-junctions-v3"
        assert body["evaluation_available"] is True

    @pytest.mark.anyio
    async def test_slow_inference_is_flagged_rather_than_called_healthy(
        self, client: TestClient, admin_token: str
    ) -> None:
        await seed_analysis(client.app, inference_ms_per_frame=250.0)

        body = client.get(MODELS, headers=auth_header(admin_token)).json()
        detector = next(model for model in body["models"] if model["role"] == "detection")

        assert detector["health"] == ModelHealth.NEEDS_ATTENTION.value
        assert "slower than real time" in detector["health_reason"]

    @pytest.mark.anyio
    async def test_a_fast_run_is_healthy_but_says_accuracy_is_unevaluated(
        self, client: TestClient, admin_token: str
    ) -> None:
        await seed_analysis(client.app, inference_ms_per_frame=20.0)

        body = client.get(MODELS, headers=auth_header(admin_token)).json()
        detector = next(model for model in body["models"] if model["role"] == "detection")

        assert detector["health"] == ModelHealth.HEALTHY.value
        assert "Accuracy is unevaluated" in detector["health_reason"]

    @pytest.mark.anyio
    async def test_p95_is_a_figure_some_run_actually_produced(
        self, client: TestClient, admin_token: str
    ) -> None:
        for index, latency in enumerate((10.0, 20.0, 90.0)):
            await seed_analysis(
                client.app, job_id=f"job-{index}", inference_ms_per_frame=latency
            )

        body = client.get(MODELS, headers=auth_header(admin_token)).json()
        latency = next(
            model for model in body["models"] if model["role"] == "detection"
        )["latency"]

        assert latency["samples"] == 3
        assert latency["p95_ms"]["value"] == 90.0, "nearest-rank, not interpolated"
        assert latency["median_ms"]["value"] == 20.0
        assert latency["slowest_ms"]["value"] == 90.0

    def test_a_driver_cannot_read_the_model_registry(
        self, client: TestClient, role_tokens: dict[Role, str]
    ) -> None:
        response = client.get(MODELS, headers=auth_header(role_tokens[Role.DRIVER]))
        assert response.status_code == 403
