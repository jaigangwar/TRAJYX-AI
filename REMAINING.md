# TRAJYX — what is left to build

Companion to [`DEVELOPMENT_STATUS.md`](DEVELOPMENT_STATUS.md), which records
what **is** built. This file records what is **not**, and how to build each
piece: where the code goes, what it must do, how to verify it, and the
constraints it has to hold to.

Everything listed here is genuinely absent. Nothing in the running product
pretends these exist — unbuilt capabilities are reported as
`UNABLE TO DETERMINE` with a reason, which is why the Model Health page says
accuracy is unevaluated instead of showing a number.

**Status at time of writing:** web app complete (13 dashboard sections), backend
complete for everything the web app needs, 341 automated tests, `verify.py`
9/9 green.

The dashboard now includes `/simulation`, a browser-only animated junction
prototype for presentations. Its traffic tracks and proximity score are
synthetic and explicitly labelled. This is not the full Phase 17 demo flow:
that still needs a repeatable seeded run through video analysis, risk zones,
alerts and report export. The ML model, mobile driver
features, production deployment and hardening are also outstanding as listed
below. The calibrated 3D conflict replay is implemented; browser interaction
and representative-camera validation remain.

---

## Ground rules for anything added here

These are not style preferences. They are the rules the existing code is built
on, and breaking one of them in new code makes the whole product untrustworthy.

1. **Never fabricate a measurement.** If a number cannot be computed from
   stored records, return `Metric.unavailable(reason)` (Python) /
   `available: false` (API) and render `—` with the reason in a tooltip. There
   is no code path in this repo that writes a KPI from a literal, and there
   must not be one.
2. **Null is not zero.** An hour with no scored event reports `mean_risk: null`
   and draws a hatched slot, not a zero bar. See
   `web/src/components/charts/Charts.tsx`.
3. **A rate needs both halves measured.** Helmet violations are counted;
   helmet *compliance rate* is refused, because nothing counts riders.
4. **Never borrow one component's figure for another.** The tracker does not
   inherit the detector's version or its latency. See
   `backend/app/api/v1/routes/models.py`.
5. **Label synthetic data everywhere it surfaces.** `origin=DEMO` flows from
   the store through the API to a `DEMO` badge, and into CSV export headers.
6. **Derive, don't duplicate.** `risk_level` is banded from `risk_score` on
   read, never stored, so a stored copy can never disagree with its source.
7. **Regenerate the contract, don't hand-edit bindings.** Change
   `shared/contracts/domain.json`, then run `python scripts/gen_contracts.py`.
   `verify.py` fails if generated files drift.

Before starting: `python scripts/verify.py` should be 9/9. After finishing:
same. Add tests in the same commit as the feature.

---

## 1. ML risk model — Phase 9

**Effort:** large (the biggest remaining item). **Blocked by:** needs labelled
data, see §1.4.

### Current state

The **explainable weighted engine** in `backend/app/risk/engine.py` remains the
live risk scorer. The ML package now includes a shared feature builder, a
JSONL dataset assembler, segment-and-time holdout, XGBoost training/evaluation
CLIs, and an artifact loader. See [`docs/ml-training.md`](docs/ml-training.md)
for the input format and exact commands. **No model has been trained or
evaluated**, because the repo still has no independently labelled corpus. The
new code refuses undersized/leaky splits and cannot manufacture accuracy
metrics from demo or heuristic output.

### What to build

**1.1 Feature pipeline** — `ml/trajyx_ml/features/build.py` · implemented

Turn a road segment plus a time window into a feature row. Read from the same
collections the geospatial aggregator uses, so training features and serving
features cannot diverge:

| Feature group | Source |
|---|---|
| Event rates per hour by type | `risk_events` |
| Minimum and mean TTC | `risk_events.details` |
| Traffic volume, vehicle-class mix | `video_analysis.class_counts` |
| Hour of day, day of week (cyclical encoding) | event timestamp |
| Segment geometry: length, lanes, speed limit, one-way | `road_segments` |
| Detector coverage flags | `video_analysis.unavailable_checks` |

Write one function used by both training and inference. A second
implementation for serving is how train/serve skew gets in.

Encode missing features explicitly (an `is_missing` companion column), never
as `0`. A segment with no volume measurement is not a segment with no traffic.

**1.2 Training** — `ml/trajyx_ml/training/train.py` · implemented; awaiting labels

XGBoost regressor targeting a risk score. Requirements:

- Split **by segment and by time**, never randomly. Random splits leak: two
  rows from the same junction an hour apart are near-duplicates, and a random
  split puts one in train and one in test, inflating the score.
- Log the exact dataset version, feature list, and hyperparameters.
- Save to `ml/artifacts/<version>/model.json` plus a `metadata.json`.

**1.3 Evaluation** — `ml/trajyx_ml/evaluation/evaluate.py` · implemented; awaiting labels

Compute MAE, RMSE, R², and calibration by risk band on the held-out split.
Then write a registry record so Model Health can display it:

```python
await store.create("model_versions", {
    "name": "trajyx-risk-xgb",
    "version": "1.0.0",
    "dataset_version": "delhi-junctions-v3",   # REQUIRED — see below
    "precision": ..., "recall": ..., "f1": ...,
    "evaluated_at": utc_now(),
})
```

`backend/app/api/v1/routes/models.py::_accuracy_from_registry` **ignores a
record with no `dataset_version`** — a precision figure with no dataset behind
it is not a measurement. Model Health will keep showing "not evaluated" until
a real evaluation run writes one. That check is deliberate; do not relax it.

**1.4 The blocker: no labelled data**

There is no ground-truth dataset in this repo, and there is no honest way to
manufacture one. Options, in order of preference:

1. Label a real corpus — needs actual CCTV footage and annotation time.
2. Use a public benchmark for the detection half only.
3. Train against the weighted engine's output — **this teaches the model to
   imitate the existing heuristic, so it cannot be reported as accuracy.** If
   you do this, the registry record must omit `dataset_version`, which keeps
   Model Health honest about it.

**1.5 Inference API** — `ml/trajyx_ml/inference/predict.py` implemented as an
artifact loader; serving endpoint and registry integration still pending in
`backend/app/api/v1/routes/risk.py`

Add `POST /risk/predict`. Return **both** scores side by side — the weighted
engine's explainable factors and the model's prediction — plus agreement. Do
not replace the explainable score with an opaque one: an operator dispatching
a patrol needs to know *why*.

If no model artifact is present, return the weighted score and state that no
model is loaded. The endpoint must not 500 when the model is absent.

### Verify

```bash
python -m pytest tests/ml -q
python scripts/verify.py
```

Tests to write: feature builder handles a segment with no video analysis;
missing features are flagged not zeroed; the split never shares a segment
across train and test; an artifact-free inference call degrades gracefully.

---

## 2. Three.js 3D visualisation — Phase 12 · IMPLEMENTED

**Core view implemented.** Browser interaction and representative-camera
visual verification remain.

`three` is already a dependency and already has its own Rollup vendor chunk
(`web/vite.config.ts`). The Analysis page lazy-loads the renderer so other
pages do not load the Three.js chunk.

### What to build

One view that earns the third dimension. The spec forbids decorative 3D, and
an extruded bar chart is decorative. The defensible candidate:

**Junction conflict view** — replay one analysed video's tracks in 3D:
ground plane from the camera's calibration, vehicle paths as ribbons over
time (height = time, so a conflict is a visible crossing), near-miss points
marked where TTC dipped. This is the one thing a 2D map genuinely cannot
show: *when* two paths occupied the same place.

Files:

- `web/src/features/analysis/ConflictView3D.tsx` — the canvas
- `web/src/features/analysis/conflict-scene.ts` — scene construction, no React
- Mounted as a tab on `web/src/pages/AnalysisPage.tsx` beside the annotated video

Data comes from `video_analysis.tracks`, `video_analysis.timeline` and the
persisted calibration snapshot. Uncalibrated tracks remain in the 2D timeline.
Check the exact shape via
`backend/app/workers/analysis.py::_track_summaries`.

### Constraints

- **2D fallback is mandatory.** Detect WebGL; if unavailable, render the
  existing timeline. Never a blank canvas.
- **Dispose on unmount** — geometries, materials, renderer. A leaked WebGL
  context per navigation will exhaust the browser's context limit.
- Match the operations aesthetic: dark ground, no reflections, no bloom, no
  orbiting auto-rotation. Risk colours come from `RISK_PRESENTATION`.
- Lazy-load with `React.lazy` so text-heavy pages never pay for Three.js.
- A track with no calibration has no metric position — do not place it in the
  scene at a guessed scale. Say the camera is uncalibrated.

### Verify

`npm run build` (watch the `three` chunk size), then
`node scripts/shots.mjs ../.verify/phase12 <email> <password> analysis` and
inspect the screenshot. Add a vitest case asserting the 2D fallback renders
when WebGL is absent.

---

## 3. Flutter mobile driver app — Phases 13–15

**Effort:** large. **Deferred by explicit instruction** ("mobile app ke liyee
ruk jao abhi wo baad ma banayenge"), so this is the last thing to pick up.

### Current state — more than a skeleton

Already working, with 19 passing tests (`flutter test`):

- `main.dart`, `core/config`, `core/network/api_client.dart`, Riverpod
  providers, theme + tokens matching the web palette
- Generated contract at `mobile/lib/core/contracts/domain.dart` (regenerated
  by `scripts/gen_contracts.py` — do not hand-edit)
- Full auth: `login_screen.dart`, `auth_controller.dart`, `auth_repository.dart`
- `app_shell.dart`, `auth_gate.dart`, `home_screen.dart`, `profile_screen.dart`

### 3.1 Driver home and risk view — Phase 13

`mobile/lib/features/risk/`

Nearby risk zones for the driver's position, ranked by distance, each showing
score, level, top factors, and its `origin` badge. Backend is done:
`POST /api/v1/risk/nearby` (see `backend/app/schemas/geo.py`).

### 3.2 GPS and the alert engine — Phase 14

`mobile/lib/features/alerts/`

The **alert decision already lives on the server** —
`backend/app/geo/service.py::evaluate_alert`, with four gates (distance by
alert level, direction/`is_ahead`, minimum risk threshold, per-user-per-zone
cooldown). All four are verified against a live API. **Do not reimplement any
gate on the device**; the client sends position, heading and speed, and
renders what comes back.

- `geolocator` for the position stream; request permission with a clear
  purpose string
- Throttle: no faster than the cooldown allows, and back off when stationary
- Render `AlertLevel` with sound/haptics; the alert card must be readable at a
  glance — a driver gets about one second
- **Privacy:** the platform stores anonymous tracking IDs and never infers
  identity. Keep a location-retention setting, default it short, and never
  upload a continuous trace when an alert check needs only the current fix.

### 3.3 Hazard reporting — Phase 15

`mobile/lib/features/report/`

Driver submits a hazard: type (`HazardType` in the contract), optional photo,
auto-filled location. It arrives as an `EventType.HAZARD_REPORT` with
`origin=MEASURED` and `review_status=PENDING`, and the existing **Incidents**
page on the web shows the queue — that side is already built and waiting.

Queue submissions locally when offline and flush on reconnect. A driver
reporting a hazard is often somewhere with no signal, which is frequently
*why* it is a hazard.

### Verify

```bash
cd mobile && flutter analyze && flutter test
python scripts/verify.py     # includes both
```

---

## 4. Deployment to Firebase — Phase 19 remainder

**Effort:** small-to-medium. **Not blocked.** Setup steps already written up
in [`docs/firebase-setup.md`](docs/firebase-setup.md).

The adapter layer is finished and this is mostly configuration. Each of
`TRAJYX_DATA_BACKEND`, `TRAJYX_AUTH_BACKEND`, `TRAJYX_STORAGE_BACKEND`
resolves to Firebase automatically when credentials are present (`auto`), so
switching should need no code change.

`backend/app/core/config.py::startup_errors()` already **refuses to start in
production** with a default JWT secret, a local adapter, or wildcard CORS.
Expect it to stop you until the environment is genuinely configured — that is
the feature working.

Remaining work:

1. Create the project; fill `.env` from `.env.example`. **Never commit the
   service-account JSON.**
2. Deploy `firebase/firestore.rules` and `firebase/storage.rules`.
3. Create the composite Firestore indexes the event queries need. Firestore
   will name the missing index in its error; add each to
   `firebase/firestore.indexes.json`.
4. Run the backend against Firebase and re-run `pytest` with
   `TRAJYX_DATA_BACKEND=firebase`.
5. Set a real retention policy for footage and evidence frames.

### Not yet present and worth adding before public exposure

- **Rate limiting** on `/auth/login` and `/videos/upload`. Upload size limits
  and content-type validation are done; request-rate limiting is not.
- **Refresh tokens.** `LocalAuthProvider` returns `refresh_token: null`; the
  field is in the schema, the rotation is not implemented.
- A content/virus scan on uploads, if footage ever arrives from outside the organisation.

---

## 5. Documentation — Phase 20

**Effort:** small. **Not blocked.**

Already written: `README.md`, `docs/architecture.md`, `docs/local-setup.md`,
`docs/firebase-setup.md`, plus `DEVELOPMENT_STATUS.md` and this file.

Still to write:

- `docs/api.md` — or simply point at the live OpenAPI at `/docs`, which is
  generated and cannot go stale
- `docs/data-honesty.md` — collect the seven ground rules above in one place,
  with the concrete examples from the code. This is the most distinctive thing
  about the project and currently it is only visible by reading source
  comments.
- `docs/cv-pipeline.md` — decode → detect → track → motion → safety checks →
  conflicts/TTC → explainable risk, and **why each detector is capability-
  gated on camera geometry**. The calibration notes in
  `cv/trajyx_cv/tracking/base.py` and `violations/detectors.py` explain
  several non-obvious decisions that took real debugging to find; they should
  not stay buried.
- A one-page demo script for showing the product: seed, upload, analyse,
  aggregate, probe the alert engine.

---

## 6. Smaller known gaps

| Gap | Where | Note |
|---|---|---|
| Live Monitoring shows registered cameras, not live streams | `web/src/pages/MonitoringPage.tsx` | Camera status is real; there is no RTSP ingest. The page does not claim otherwise. |
| No PDF export | `backend/app/services/report_service.py` | CSV and JSON are done. PDF needs a renderer (WeasyPrint/ReportLab) and a layout; the `ExportFormat` enum is the place to add it. |
| Report history is unpaginated | `backend/app/api/v1/routes/reports.py` | Capped at 30, newest first. Fine until report volume grows. |
| Violation register capped at 500 rows | `report_service.py::_violations` | Stated in the section note. Needs cursor paging for a bigger corpus. |
| `tracker_version` is never recorded | `backend/app/workers/analysis.py` | Which is why Model Health shows "version not recorded" for ByteTrack. Fix by writing the field in the worker; the API already reads it. |
| No trip recording | `trips` collection declared in the contract, unused | Phase 14 territory. |
| Notifications collection unused | `notifications` in the contract | Push delivery not built. |
| `recharts` is an unused dependency | `web/package.json`, `VENDOR_CHUNKS` in `web/vite.config.ts` | Charts ended up hand-rolled SVG instead. Nothing imports it, so it is not bundled, but it should be dropped from `package.json` and from `VENDOR_CHUNKS` on the next dependency pass. |

---

## 7. Git

Nothing has been pushed. Six local commits exist through the risk-map fix;
everything after that (Analytics, Reports, Model Health, the honesty fixes,
the new tests, these docs) is **uncommitted on disk** by request.

A push to `github.com/jaigangwar/TRAJYX-AI` currently fails **403**: the
stored credential belongs to GitHub user `Vann781`. To resolve, either add
`Vann781` as a collaborator on that repository, or switch the stored
credential to the `jaigangwar` account.

---

## Suggested order

1. **Documentation** (§5) — cheap, and `docs/data-honesty.md` captures design
   reasoning while it is still fresh.
2. **Mobile app** (§3) — large, but the server side it needs is already done
   and verified, so it is mostly UI against working endpoints.
3. **Firebase deployment** (§4) — do this before the ML model; a trained model
   is worth little without somewhere real to serve it from.
4. **ML risk model** (§1) — last, because §1.4 needs a data decision that no
   amount of code will settle.
