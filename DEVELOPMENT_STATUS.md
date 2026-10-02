# TRAJYX — development status

This file is the authoritative record of what is implemented, what is not, and
what was actually verified. It is updated at the end of every phase.

Anything not listed as complete below does not exist, regardless of how the
interface may look. What is *not* built, and how to build it, is recorded in
[`REMAINING.md`](REMAINING.md).

**Last updated:** 2 October 2026 — ML workflow and calibrated 3D replay added
**Complete:** Phases 0–8, 10–12, 16; phase 9 training/evaluation tooling is implemented
but has no labelled data or evaluated model; phase 17 has a presentation simulation
prototype, not the full seeded demo flow.
**Deferred:** Phases 13–15 (driver mobile features), by request. Production
deployment/hardening and parts of phase 20 remain — see `REMAINING.md`.

## Verification summary

Last recorded full baseline: `python scripts/verify.py` — 9/9 checks and 341
automated tests passed before the latest work. This update's web production
build passed; automated tests were not rerun. The configured Python launcher
currently points to an inaccessible Windows Store runtime, so Python compile
and ML workflow checks could not be run in this environment.

| Component | Check | Result |
|-----------|-------|--------|
| contracts | generated bindings current | PASS |
| lint | ruff (backend, cv, ml, scripts, tests) | PASS — 0 findings |
| python | pytest | PASS — 274 tests |
| web | oxlint | PASS — 0 warnings |
| web | tsc typecheck (strict) | PASS — 0 errors |
| web | vitest | PASS — 48 tests |
| web | production build | PASS |
| mobile | dart analyze | PASS — 0 issues |
| mobile | flutter test | PASS — 19 tests |

**341 automated tests in the last full baseline.** Plus real-browser verification via Playwright:
sign-in (`web/scripts/e2e-login.mjs`, 7/7), page rendering
(`web/scripts/shots.mjs`), and the report export download
(`web/scripts/shot-reports.mjs`).

### Web application — 13 dashboard sections

| Page | State |
|---|---|
| Overview | Counted KPIs, recent events, pipeline readiness |
| Live Monitoring | Camera registry and status. No RTSP ingest — the page does not claim live streams |
| Video Analysis | Upload, progress, annotated playback, 2D timeline, calibrated 3D conflict replay, explainable risk readout |
| Simulation | Synthetic junction replay with explicit DEMO labels and playback controls |
| Cameras | Registry CRUD, geometry configuration, detector capability gating |
| Risk Map | MapLibre GIS: risk-coloured segments, computed zones, camera coverage, alert-engine probe |
| Violations / Near Misses / Incidents | Three views over the one shared event model |
| Analytics | Hourly/weekday/daily activity, mean risk by hour, breakdowns, detector coverage, segment ranking |
| Reports | Five report types, stored history, CSV + JSON export |
| Model Health | Registry derived from actual runs, measured latency, refused accuracy |
| Settings | Deployment state, adapter backends, retention |

No placeholder page is left. `PhasePendingPage` was deleted when the last
section it stood in for was built.

## Phase 12 — Calibrated 3D conflict replay · IMPLEMENTED

- The analysis record keeps the camera calibration snapshot used by that run.
  If the video dimensions do not match configured camera dimensions, the
  snapshot is withheld and the 3D tab stays disabled.
- A lazy-loaded Three.js view places each calibrated path on an estimated
  ground plane and uses height for time. Near-miss entries mark the replay;
  orbit controls are manual and all geometries/materials/renderer resources
  are disposed on unmount.
- The 2D timeline remains available and is selected when WebGL cannot start.
  Pixel paths are never presented at a guessed metric scale.
- Production web build passes. Representative-camera and interactive browser
  verification remain outstanding.

## Phase 9 — ML training and evaluation workflow · PARTIAL

- Implemented one feature builder for both offline training and later
  inference, with explicit missing-feature flags.
- Added versioned JSONL-to-CSV dataset assembly, whole-segment plus future-time
  holdout, XGBoost training, evaluation (MAE/RMSE/R² and risk-band
  precision/recall/F1/calibration), and a model artifact loader.
- No model has been trained or evaluated: the repository has no independently
  labelled risk corpus. The evaluation workflow refuses undersized splits;
  synthetic demo records and weighted-engine outputs are not ground truth.
- Input format and reproducible commands: [`docs/ml-training.md`](docs/ml-training.md).
- Prediction API and model registry integration remain pending. Live risk
  alerts continue to use the explainable weighted engine.

---

## Phase 16 — Reports & export · COMPLETE

- `ReportService` builds five report types — daily operations, weekly summary,
  road safety, violation register, risk hotspots — over the **same** analytics
  aggregation the Analytics page uses, so a report and the page for the same
  window cannot disagree.
- A report is a list of titled tables, so the web view, the CSV writer and the
  JSON export are one implementation rather than three, and a new report type
  adds a builder rather than a new endpoint, schema and exporter.
- Each run is **persisted with its parameters** and rendered from the stored
  document, never re-computed on open. A report whose numbers change when
  reopened is not a record of anything — verified by a test that adds events
  after generation and asserts the stored figure does not move.
- Sections that cannot be computed are **kept and marked unavailable** rather
  than dropped, so a reader is never left guessing whether a missing section
  means "nothing happened" or "we cannot tell".
- CSV carries a provenance header: generated-at, account, window, period,
  record count, synthetic count, and an explicit `NOTE` line when any record
  is synthetic. Absent values stay empty cells — never 0, which a spreadsheet
  would happily average.
- `Content-Disposition` is exposed through CORS, so the browser saves the
  server-named file (`trajyx-road-safety-20260912-1256.csv`) rather than a
  fallback. Verified by a real download in Playwright.

**Endpoints:** `GET /reports/types`, `GET /reports`, `POST /reports`,
`GET /reports/{id}`, `GET /reports/{id}/export?format=csv|json`

---

## Phase 11 — Analytics · COMPLETE

- One endpoint (`GET /analytics/summary`) serves the whole page from a single
  read of the event window. Per-chart endpoints would re-read the same events
  for every panel, and would let two panels on one screen describe different
  windows.
- Activity by hour of day, by weekday and by day; events by type, category,
  severity and origin; traffic composition from detections; detector coverage;
  road segments ranked by risk.
- **A bucket with no scored event reports `mean_risk: null`** and the chart
  draws a hatched slot, not a zero bar. An hour in which nothing was scored
  and an hour in which everything scored zero are different facts about a
  road.
- **Helmet compliance rate is refused**, with the reason: the violation count
  is known, the rider population is not, so the denominator is unknown.
  `violations / detections` would look like a compliance rate and would not be
  one.
- Traffic composition distinguishes **"no analysis ran"** from **"analysis ran
  and classified no vehicles"** — different problems to go and investigate.
- Chart primitives are hand-rolled SVG (`web/src/components/charts/Charts.tsx`)
  rather than a charting library: a trend line breaks across a gap instead of
  interpolating through it, which is how a chart comes to assert something
  nobody measured.

---

## Model registry & health · COMPLETE

- A model version appears **because an analysis run used it**, not because a
  row was added. The registry is structurally unable to list a model the
  platform has never executed.
- Measured inference latency — mean, median, p95, slowest. p95 is nearest-rank,
  so it is always a figure some run actually produced rather than an
  interpolated value between two runs.
- **Precision, recall and F1 are reported as unavailable** unless a recorded
  evaluation run against a *named dataset* produced them. A registry record
  with no `dataset_version` is ignored. Detection confidence is never
  substituted — it is the model's own certainty, not a measure of correctness.
- Health is derived only from what is measured: job failure rate and inference
  speed, with the thresholds stated on the page. A model marked HEALTHY is
  fast and does not crash; the page says in as many words that this is not a
  claim about whether its detections are correct.
- **No figure is borrowed between components.** ByteTrack does not inherit the
  detector's version (shows "version not recorded") or its per-frame latency
  (reported unavailable, health `UNKNOWN`). Both were bugs found during
  verification of this phase; both are now regression-tested.

---

## Phase 10 — GIS risk heatmap & driver alerts · COMPLETE

- `GeoService`: haversine distance, bearing clockwise from north,
  equirectangular segment projection, bounding-box pre-filter, `is_ahead`
  direction gate.
- Event attribution to road segments within 60 m; zone aggregation at a 140 m
  influence radius. Aggregation **clears zones first**, so a segment that goes
  quiet stops warning drivers. Only non-LOW segments become zones. A zone
  inherits `origin=DEMO` if any source event was synthetic.
- Explainable risk engine with weighted named factors summing to 100 and
  documented saturating references. The references were recalibrated after
  discovering the originals were roughly 100x too high, which made every real
  road score LOW and meant **zero risk zones were ever created — the system
  would never have warned anybody.**
- Driver alert engine with four gates: distance per alert level, direction
  (ahead only), minimum risk threshold, and per-user-per-zone cooldown. All
  four verified against a live API.
- Risk Map page with MapLibre, no API key required. Clicking empty map probes
  the alert engine at that point, which is how an operator checks what a
  driver would actually be told there.

**Notable bug:** the risk overlay rendered nothing while every source and
layer existed and the API returned correct data. The cause was Vite's
dependency optimiser rewriting MapLibre's entry without copying the sibling
module worker it spawns, so the worker request failed **silently** — no error
event, no console output — leaving every GeoJSON source permanently unparsed
while the raster basemap drew normally. Isolated by adding a fresh source and
layer with inline data and a static colour, which also rendered nothing, ruling
out the paint expressions and the React sync. Fixed with `optimizeDeps.exclude`
and documented in `web/vite.config.ts`.

---

## Phases 3–8 — Video analysis pipeline · COMPLETE

Upload with size and type validation → async job with progress → decode →
YOLO detection → ByteTrack → motion estimation → safety detectors → pairwise
conflicts and TTC → explainable risk. Annotated video written with persistent
track IDs and trails.

Detectors are **capability-gated on camera geometry**: calibration, lane
regions, stop line and signal phase each determine which checks can run, and
unavailable checks are reported with reasons rather than silently skipped.

Five real bugs were found by running the pipeline on a clip and inspecting the
output, rather than by trusting the tests:

| Bug | Cause | Fix and effect |
|---|---|---|
| Wrong-way undetectable by construction | Compared heading to the *closest* lane's heading | Lane regions plus position-based lane selection |
| 52 phantom hard-brakes | 34 m/s² accelerations from unsmoothed speed | Speed smoothing and a plausibility gate; 52 → 5 |
| Lane-change misfires | Frame-clipped bounding-box width (a 78px car read as 11px) | Median width across the track |
| 24 near misses in 12 s | Gap jitter | Gap smoothing, convergence requirement, 2-frame persistence; 24 → 9 |
| Nothing tracked at all | ByteTrack's published `0.8` is a threshold on a `1 - IoU` cost matrix, not an IoU score | Set to `0.25`, with the reasoning documented in `cv/trajyx_cv/tracking/base.py` |

---

## Phase 2 — Web dashboard foundation · COMPLETE

- Authenticated shell: sidebar navigation grouped by Operations / Intelligence
  / Administration, page header with deployment badges (demo mode, data
  backend, environment), theme toggle, role-aware menu.
- The route table reads its role lists **from the navigation table**, so the
  menu and the router cannot disagree — a test asserts the two agree, and a
  deep link cannot reach a section the sidebar hides. The API enforces the
  same boundaries independently.
- Four explicit data states everywhere (`AsyncBoundary`): loading skeletons,
  empty with a hint about what would fill it, actionable error carrying the
  API envelope's code and message, and loaded.
- **One shared event model.** Violations, near misses, driver reports and
  behaviour events are one collection with one shape, so the three list pages,
  the map layers and the exports are all views over the same query path rather
  than parallel implementations. `category` and `risk_level` are derived on
  read, never stored.
- `Metric` type with `available: false` plus `unavailable_reason`, rendered as
  `—` with the reason in a tooltip. Tested: a metric nothing has produced must
  not render as 0.
- Camera registry with status, location, and the geometry that decides which
  detectors can run.
- Design language fixed in `web/src/styles/tokens.css` — dense operations
  console, plain hex risk palette, no gradients, no glassmorphism, risk always
  carried by colour **and** a text label so colour is never the only carrier
  of meaning.

---

## Phase 1 — Authentication, roles & database · COMPLETE

### Persistence

- `DocumentStore` interface with a restricted operator set, cursor paging and
  typed filter/query builders. Offset paging is deliberately absent — Firestore
  cannot serve it, so offering it would mean a query that works in development
  and fails in production.
- `LocalDocumentStore` — on-disk JSON, one file per collection, per-collection
  `asyncio.Lock`, atomic writes through a temp file plus `os.replace`, file I/O
  on a worker thread. Datetimes are tagged on write so they come back as
  `datetime` rather than degrading to strings, which would silently turn every
  later comparison into a string comparison.
- `FirestoreDocumentStore` — same interface. Blocking SDK calls dispatched to
  threads, `DatetimeWithNanoseconds` normalised, 500-write batching,
  server-side `count()`, and transport failures translated to
  `DEPENDENCY_UNAVAILABLE` instead of an opaque 500.
- `ObjectStorage` interface with local and Firebase Storage adapters, key
  validation against path traversal, and a centralised key layout so the code
  and `firebase/storage.rules` cannot drift apart.

### Identity

- `AuthProvider` interface with two implementations chosen by
  `TRAJYX_AUTH_BACKEND`. Both run through the same authorisation dependencies,
  so the checks that actually protect CCTV-derived data are the ones under test.
- `LocalAuthProvider` — bcrypt credentials, signed JWT sessions. The role is
  re-read from the store on every request, so a role change or a suspension
  takes effect immediately rather than waiting for the token to expire.
- `FirebaseAuthProvider` — ID-token verification with `check_revoked`, the role
  stored as a Firebase custom claim (which is what lets the Firestore rules
  enforce roles without reading a user document), claim/document mismatch
  repair, and first-sign-in provisioning at the least-privileged role.
- `PasswordHasher` — bcrypt used directly. Passwords are SHA-256 plus base64
  pre-hashed to a fixed 44 bytes, so a long passphrase cannot be silently
  truncated at bcrypt's 72-byte limit. An unknown address is verified against a
  dummy hash of the same cost, so login timing does not reveal which addresses
  are registered. Cost is configurable and floored at 10 outside tests.

### Authorisation

- Dependencies: `require_staff`, `require_admin`, `require_operator`,
  `require_analyst`, `require_driver`, `require_roles(...)`, and
  `require_self_or_admin` for per-user resources.
- Enforced server-side on every protected route. The dashboard also hides
  sections a role cannot use, but that is convenience — a hand-written request
  is refused identically.

### API surface (17 routes)

- `POST /auth/login`, `POST /auth/firebase`, `GET|PATCH /auth/me`,
  `POST /auth/register`, `POST /auth/bootstrap-admin`,
  `POST /auth/change-password`, `POST /auth/logout`.
- `GET|POST /users`, `GET /users/{id}`, `PATCH /users/{id}/role`,
  `PATCH /users/{id}/status`, `DELETE /users/{id}`.
- Invariants live in `UserService`, not in handlers: the last administrator
  cannot be demoted, suspended or deleted; a staff-role downgrade revokes
  sessions immediately; self-service edits cannot reach role or status, because
  the request schema has no such fields.

### Web

- Session verified against `/auth/me` before the app renders, so the role
  driving every permission check comes from the server, never from the stored
  copy. A tampered `localStorage` entry therefore grants nothing.
- The token lives in a module-scoped holder rather than a React ref: it is not
  render state, and keeping the API client in step meant reading a ref during
  render, which is the pattern React warns about.
- Login page, `RequireAuth` / `RequireStaff` / `RequireRole` guards that read
  the same role lists `navigation.ts` declares, profile menu with sign-out, and
  a driver-notice page for valid accounts that belong in the mobile app.
- Session in `localStorage`, or `sessionStorage` when "remember me" is off. The
  trade-off against an HttpOnly cookie is documented in `session-store.ts`.

### Mobile

- Session stored in the Android Keystore via `flutter_secure_storage`, not
  cleartext preferences — a bearer token in plain preferences is readable by
  anything with filesystem access on a rooted device.
- `AuthController` state machine: restoring → signed in / signed out, with a
  splash so a returning driver never sees the login form flash.
- Offline at launch keeps the stored session, because a dead connection on the
  road must not lock a driver out of cached risk zones.
- Login and registration screen, profile screen with sign-out confirmation, and
  a staff account signing into the driver app is turned away with an
  explanation rather than a permission error.

### Tooling

- `scripts/seed_admin.py` — the supported bootstrap path, including in
  production. Refuses once any administrator exists.
- Root `pytest.ini`, replacing the config under `backend/pyproject.toml`.
- `web/scripts/e2e-login.mjs` — real-browser end-to-end sign-in check.

### End-to-end verification

Against a live API using the local adapters:

- `seed_admin.py` created the first administrator. The stored record was
  inspected and contains a bcrypt hash at cost 12 and **no plaintext**.
- Login returns a usable token; `/auth/me` returns the profile; no token → 401;
  wrong password → 401; admin creates an operator → 201; operator lists users →
  **403**; operator creates an admin → **403**; operator PATCHes their own role
  → **422**; a second bootstrap attempt → **403**.
- Real browser, 7/7: protected route redirects to login, sign-in reaches the
  dashboard, live API data renders, session survives a reload, profile menu
  shows the identity, sign-out clears storage, the route is protected again
  afterwards. No console errors.

### Bugs found and fixed

1. **passlib is unusable with bcrypt 5.x.** Its backend probe hashes a
   >72-byte secret, which bcrypt now rejects, so every import of the auth
   module raised. Replaced with `bcrypt` directly plus pre-hashing.
2. **A 422 echoed the submitted password.** The validation handler passed
   `exc.errors()` straight into the response, and each entry carries the
   offending `input` — so a rejected registration returned the caller's
   password in the body, and into any log that records responses. Now only
   `loc`, `msg` and `type` are copied. Regression test added.
3. **A custom validator failure returned 500 instead of 422.** Pydantic puts
   the original exception object in `ctx`, which is not JSON-serialisable.
   Same fix; regression test added.
4. **Public registration accepted weaker passwords than the admin endpoint.**
   The strength rule lived only on `UserCreateRequest`, so `/auth/register`
   accepted `alllowercase`. Extracted into a shared `StrongPassword` type used
   by every path that sets a password.
5. **42 async tests were silently skipped.** pytest resolved rootdir to the
   repository root and so never read `backend/pyproject.toml`; `asyncio_mode`
   was unset, every async test was skipped, and the run still reported green.
   Config moved to a root `pytest.ini`.
6. **`change-password` took the password as a query parameter**, where it would
   be recorded in access logs, proxy logs and browser history. Moved to a
   request body. (Found alongside FastAPI rejecting `Annotated` combined with a
   `Depends` default.)
7. **The bcrypt cost made the suite unusable.** 71 tests took 144 seconds at
   cost 12. Cost is now configurable, 4 in tests and floored at 10 everywhere
   else: 12 seconds for the same tests.
8. Riverpod 3 removed `AsyncValue.valueOrNull`; a mobile test stub was not a
   real `SocketException`, so the offline path was never actually exercised.

### Known limitations

- **The Firebase paths are untested against a live project.** Both adapters are
  written and reviewed, and the local paths carry 216 tests, but no Firebase
  project has been connected. Deploying the rules and exercising the emulator is
  outstanding.
- **Local JWTs cannot be revoked individually.** They are stateless, so
  `/auth/logout` cannot invalidate a specific token — the client discards it and
  it expires on schedule. Suspension *is* immediate, because the user document
  is re-read per request. This is one reason the local backend is refused in
  production.
- **No rate limiting on sign-in.** Timing is equalised and messages do not
  reveal whether an address exists, but nothing throttles repeated attempts.
  Phase 19.
- **No password reset or email verification** on the local path. Firebase
  provides both; the local provider is development-only.
- **No audit log.** Role and status changes are logged through structlog but not
  persisted as queryable records. Phase 19.
- **The dashboard still shows no traffic data.** Overview reports platform state
  only. KPIs arrive in phase 2, once there is data behind them.
- **`flutter pub get` prints desktop-plugin warnings.** Cosmetic: the project is
  Android-only, so Flutter cannot resolve the Windows/Linux default
  implementations of `path_provider`. Android builds are unaffected.

### Next phase

**Phase 2 — Web dashboard foundation**

- Camera registry with CRUD, location and road-segment assignment.
- Overview KPIs backed by real stored records.
- Events page built on the shared event model.
- Base map with the camera layer.
- Settings page: users, alert thresholds, retention, demo mode.
- A reusable `DataTable` with sorting, filtering and the four data states.

---

## Phase 0 — Foundation & monorepo · COMPLETE

### Completed features

**Monorepo and tooling**

- Structure: `backend/`, `web/`, `mobile/`, `cv/`, `ml/`, `shared/`,
  `firebase/`, `scripts/`, `tests/`, `docs/`, `models/`, `datasets/`,
  `assets/`.
- `.gitignore` covering secrets, virtualenvs, `node_modules`, Flutter build
  output, model weights and video; `.gitattributes` normalising line endings.
- `scripts/verify.py` — every check across all components, one summary.
  A missing toolchain reports `SKIP`, not `FAIL`.
- `scripts/dev_api.py` — starts the API with reload using the repo venv,
  without requiring shell activation.

**Shared domain contract**

- `shared/contracts/domain.json` — the single source of truth: 16 enums, risk
  bands, TTC bands, alert-threshold defaults, event-category map, and 18
  collection names.
- `scripts/gen_contracts.py` generates TypeScript, Python and Dart bindings,
  with `--check` failing the build when any binding is stale. Risk banding is
  therefore defined once and tested identically in three languages.

**Backend**

- Application factory with lifespan validation, CORS, security headers, and a
  request-context middleware that assigns and echoes `X-Request-ID`.
- Environment-driven settings with no hardcoded URLs or secrets, and `auto`
  resolution of the data, auth and storage adapters.
- One error envelope with a typed taxonomy; internals are logged, never
  returned.
- Structured logging: console in development, JSON in staging and production.
- `GET /api/v1/health` reports the *resolved* adapter per subsystem plus a
  human-readable warning for each degraded mode.
- Startup fails in production on the default JWT secret, a local adapter, or a
  wildcard CORS origin.

**Web dashboard**

- Design system: layered charcoal surfaces, the brand teal as the only accent,
  the safety ramp reserved for risk semantics, 2-6px radii, 1px borders, an
  11-13px type scale, tabular numerals. Full light theme via token overrides.
- Shell with a collapsible role-grouped navigation rail, top bar with live
  capability chips, and a theme toggle.
- Routes for all 12 sections with role visibility declared once in
  `navigation.ts`; a test asserts the menu and router cannot drift.
- Four-state UX contract enforced by `AsyncBoundary`, so no data region can
  render blank.
- Typed API client with error-envelope decoding, Zod response validation and
  request-id propagation.
- `PhasePendingPage` naming the delivering phase, with no invented metrics.
- Hand-drawn 16px icon set (37 glyphs) and an inline-SVG brand mark; no icon
  library dependency.

**Mobile**

- Android project, dark-only Material 3 theme mirroring the web tokens, 52px
  touch targets, tabular figures for live readouts.
- Six-destination bottom navigation; `TrajyxMark` painted with `CustomPainter`
  so the brand is resolution-independent.

**CV and ML packages**

- Coordinate conventions fixed once: pixel origin top-left, `xyxy` boxes,
  angles in `[0, 360)` clockwise from image-up — matching compass bearing, so
  image-space and GPS headings share one comparison function.
- `BoundingBox` with IoU, containment, clipping and a `bottom_center`
  ground-contact reference point; slotted dataclasses sized for per-frame
  allocation.
- Track class assignment by majority vote, so one misread frame cannot change
  a vehicle's class.
- `Detector` and `Tracker` protocols with provenance types. COCO mapping
  returns `None` for classes the stock weights cannot distinguish (scooter,
  auto-rickshaw) rather than inventing a capability.

**Firebase**

- Deny-by-default Firestore rules; analysis output is unwritable by every
  client role; a user cannot change their own role.
- Storage rules keep footage staff-only and cap driver uploads to images.
- 15 composite indexes, each annotated with the query that requires it.

### Tests run

10/10 checks — 82 automated tests across backend, cv, web and mobile, plus
ruff, oxlint, strict tsc, dart analyze and a production web build. Dashboard
render verified by screenshot at 1600×1000 with no console errors.

### Bugs found and fixed

1. `structlog` configured with `WriteLoggerFactory` while using
   `add_logger_name`, which needs a stdlib logger — this crashed every request.
2. `average_bearing` returned `360.0` instead of `0.0` when averaging across
   north, because `% 360` on a tiny negative float yields `360.0`, outside the
   documented `[0, 360)` range.
3. Two React fast-refresh warnings from exporting hooks beside components.
4. TypeScript 6 deprecating `baseUrl`, and Rollup 8 rejecting the object form
   of `manualChunks`.
