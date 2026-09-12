# TRAJYX architecture

> Status: this document describes the intended architecture in full. Sections
> covering components that are not implemented yet say so explicitly and name
> the phase that delivers them. See [DEVELOPMENT_STATUS.md](../DEVELOPMENT_STATUS.md)
> for what actually works today.

## 1. The idea

Conventional traffic enforcement systems **detect violations after they
happen**. TRAJYX **understands road behaviour, predicts risky situations, and
warns drivers before they reach a dangerous place**.

The loop:

```
OBSERVE  ->  TRACK  ->  UNDERSTAND  ->  PREDICT  ->  WARN  ->  LEARN
```

- **Observe** — CCTV or uploaded footage is decoded and objects are detected.
- **Track** — detections are given persistent identities across frames.
- **Understand** — identities become trajectories: speed, heading, lane
  behaviour, braking, violations.
- **Predict** — pairwise interactions produce estimated time-to-collision,
  near misses, and a risk score per road segment and time of day.
- **Warn** — the driver app matches GPS position and heading to a road
  segment and warns before the driver enters a relevant high-risk zone.
- **Learn** — confirmed hazards, operator review decisions and observed
  outcomes feed back into the risk model.

## 2. Component map

```
                       ┌─────────────────────────┐
   CCTV / uploaded ───► │  Analysis worker        │
   video                │  (cv/ + ml/ packages)   │
                       └───────────┬─────────────┘
                                   │ detections, tracks, events, risk
                                   ▼
┌──────────────┐          ┌────────────────────┐         ┌──────────────────┐
│ Web dashboard│ ◄──────► │  FastAPI backend   │ ◄─────► │  Firestore       │
│ (web/)       │   REST   │  (backend/)        │ adapter │  or local store  │
└──────────────┘          │                    │         └──────────────────┘
                          │  risk engine       │         ┌──────────────────┐
┌──────────────┐          │  geo engine        │ ◄─────► │  Object storage  │
│ Driver app   │ ◄──────► │  alert engine      │ adapter │  Firebase/local  │
│ (mobile/)    │   REST   └────────────────────┘         └──────────────────┘
└──────────────┘
```

Both clients talk to the same backend and therefore to the same intelligence.
There is no second, separate "mobile logic": the alert engine that decides a
driver should be warned is the same code that the dashboard queries to explain
why a segment is risky.

## 3. Repository layout

| Path        | Contents |
|-------------|----------|
| `backend/`  | FastAPI service: API, risk engine, geo engine, repositories, workers |
| `web/`      | React + TypeScript operator and analyst dashboard |
| `mobile/`   | Flutter driver application (Android first) |
| `cv/`       | Computer-vision package: detection, tracking, trajectory, conflicts |
| `ml/`       | Risk-model features, training, evaluation, inference |
| `shared/`   | Canonical domain contract and its generated language bindings |
| `firebase/` | Firestore rules, indexes, Storage rules |
| `scripts/`  | Contract generation, dev servers, verification |
| `tests/`    | Backend, CV, geo, risk and integration tests |
| `docs/`     | This documentation set |
| `models/`   | Model weights and evaluation artifacts (gitignored) |
| `datasets/` | Training and sample data (gitignored except samples) |

## 4. The shared domain contract

`shared/contracts/domain.json` is the single source of truth for every enum,
risk band and threshold in the product. `scripts/gen_contracts.py` generates:

- `shared/ts/domain.ts` — consumed by the web app
- `shared/python/trajyx_shared/domain.py` — consumed by backend, CV and ML
- `mobile/lib/core/contracts/domain.dart` — consumed by the Flutter app

This exists because the alternative — redeclaring `RiskLevel` in three
languages — guarantees that one day the dashboard will call 74 "High" and the
driver app will call it "Moderate". `python scripts/gen_contracts.py --check`
runs in verification and fails the build if any binding is stale.

## 5. Adapter boundaries

Three subsystems are pluggable, selected by environment variable, each
resolving `auto` to the cloud implementation when credentials exist and to a
local implementation otherwise:

| Concern | Variable | Cloud | Local fallback |
|---------|----------|-------|----------------|
| Operational data | `TRAJYX_DATA_BACKEND` | Firestore | On-disk JSON document store |
| Identity | `TRAJYX_AUTH_BACKEND` | Firebase Authentication | Self-issued development tokens |
| Object storage | `TRAJYX_STORAGE_BACKEND` | Firebase Storage | Local filesystem |

Consequences:

- The whole stack runs end to end on a clean checkout with no cloud project.
- `GET /api/v1/health` reports which adapter actually resolved, and the
  dashboard displays it. A degraded mode is never invisible.
- Startup **fails** if a local adapter is selected while
  `TRAJYX_ENVIRONMENT=production`.

### Migration path to PostgreSQL + PostGIS

Firestore suits operational application data — users, cameras, jobs, events,
alerts — but it is a poor fit for the analytical and geospatial workloads that
grow fastest: "risk by hour across 400 segments for the last 30 days", or
"segments within 800 m of this point along this heading".

The design keeps that migration from becoming a rewrite:

- All persistence goes through repository interfaces in
  `backend/app/repositories/`. No route or engine imports a Firestore client.
- Geospatial predicates live in `backend/app/geo/`, expressed over plain
  coordinates. They are the functions PostGIS would replace with `ST_DWithin`
  and friends.
- Events carry explicit `road_segment_id` and coordinates rather than relying
  on document nesting, so they are relationally shaped already.

## 6. Data honesty contract

The product is a safety system. Presenting a guess as a measurement is the
worst failure it could have, so three rules are enforced in the type system
rather than left to reviewer discipline:

1. **Every record carries an origin** — `MEASURED`, `ESTIMATED` or `DEMO`.
   The UI renders a chip for the latter two; the absence of a chip *means*
   measured.
2. **Visual checks are tri-state** — `DETECTED`, `NOT_DETECTED`,
   `UNABLE_TO_DETERMINE`. Poor visibility yields the third, never the second.
   A helmet that cannot be seen is not an absent helmet.
3. **No metric is authored by hand.** Model precision, recall and F1 come
   only from a recorded evaluation run. There is no code path that writes a
   performance number from a literal.

Derived rules that follow from these: speed is only estimated where camera
calibration supports it, TTC is always labelled "estimated", and red-light
violations are not emitted when signal phase is `UNKNOWN`.

## 7. Privacy by design

- No face recognition and no licence-plate reading.
- Track identifiers are per-video anonymous counters, not reused across videos
  and not correlated between cameras.
- Detections and tracking events are staff-only; drivers can read aggregate
  risk zones and road segments, never footage-derived detail about individuals.
- Retention is configurable per data class
  (`TRAJYX_RETENTION_DAYS_DETECTIONS`, `TRAJYX_RETENTION_DAYS_EVENTS`).

## 8. Asynchronous analysis

Video analysis takes minutes; HTTP requests must not. The flow is:

```
POST /videos/upload  -> stored, job created (QUEUED)
POST /videos/analyze -> job accepted, returns immediately
        worker       -> PROCESSING -> COMPLETED | FAILED
GET  /videos/{id}    -> current status and progress
```

The MVP worker runs in-process behind a `JobQueue` interface. Because routes
depend on that interface rather than on the implementation, moving to Redis +
RQ with GPU workers is a change of one binding, not a redesign.

*Not implemented yet — phase 3.*

## 9. Coordinate conventions

Fixed once, in `cv/trajyx_cv/types.py`, because a mismatch here corrupts
everything downstream silently:

- Pixel space: origin top-left, x right, y **down** (OpenCV).
- Boxes: `xyxy` absolute pixels, inclusive of `x1,y1`, exclusive of `x2,y2`.
- Angles: degrees in `[0, 360)`, clockwise from image-up.

The angle convention deliberately matches compass bearing, so image-space
headings and GPS headings can be compared by the same function — which is what
lets wrong-way detection and the driver's "is this zone ahead of me?" check
share code.

The ground-contact reference point for a vehicle is the **bottom centre** of
its box, not the centre: on a road-facing camera the bottom edge approximates
where the vehicle meets the road surface, and projecting the centre instead
places the vehicle metres away from where it is.

## 10. Phase plan

The build order is deliberate: each phase is verifiable on its own, and no
phase depends on a later one.

| Phase | Deliverable | State |
|------:|-------------|-------|
| 0 | Monorepo, contracts, skeletons, design system | **Complete** |
| 1 | Authentication, roles, database layer | Pending |
| 2 | Dashboard foundation with real data | Pending |
| 3 | Video upload and async jobs | Pending |
| 4 | YOLO detection | Pending |
| 5 | Multi-object tracking | Pending |
| 6 | Safety and violation detection | Pending |
| 7 | Trajectory and interaction analysis | Pending |
| 8 | Near-miss and collision risk | Pending |
| 9 | ML risk model | Pending |
| 10 | GIS risk map | Pending |
| 11 | Analytics | Pending |
| 12 | 3D visualisation | Pending |
| 13 | Mobile driver app | Pending |
| 14 | GPS and smart alerts | Pending |
| 15 | Driver hazard reporting | Pending |
| 16 | Reports and export | Pending |
| 17 | Demo mode | Pending |
| 18 | Testing | Pending |
| 19 | Hardening | Pending |
| 20 | Documentation | Pending |

## 11. Future architecture

The MVP is shaped so these extend it rather than replace it:

- Multiple cameras and real-time RTSP ingest (the `Detector`/`Tracker`
  protocols are already per-frame and stateless across videos).
- GPU inference workers behind the same `JobQueue` interface.
- Edge inference on camera-adjacent hardware, publishing events to the same
  API.
- Weather, fog and flooded-road detection as additional
  `SafetyDetector` implementations.
- Fleet management and insurance analytics as consumers of the existing
  event and risk APIs.
