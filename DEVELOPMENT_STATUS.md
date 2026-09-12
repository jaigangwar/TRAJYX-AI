# TRAJYX — development status

This file is the authoritative record of what is implemented, what is not, and
what was actually verified. It is updated at the end of every phase.

Anything not listed as complete below does not exist, regardless of how the
interface may look.

**Last updated:** Phase 0 completion
**Current phase:** 0 of 20 — complete
**Next phase:** 1 — Authentication, roles and database layer

---

## Phase 0 — Foundation & monorepo · COMPLETE

### Completed features

**Monorepo and tooling**

- Repository structure: `backend/`, `web/`, `mobile/`, `cv/`, `ml/`,
  `shared/`, `firebase/`, `scripts/`, `tests/`, `docs/`, `models/`,
  `datasets/`, `assets/`.
- Git initialised with `.gitignore` covering secrets, virtualenvs,
  `node_modules`, Flutter build output, model weights and video files; and
  `.gitattributes` normalising line endings.
- `scripts/verify.py` — runs all 10 checks across five components and prints
  one summary. Missing toolchains report `SKIP`, not `FAIL`.
- `scripts/dev_api.py` — starts the API with reload, using the repo venv
  without requiring shell activation.
- Root `package.json` with orchestration scripts.

**Shared domain contract**

- `shared/contracts/domain.json` — single source of truth: 16 enums, risk
  bands, TTC bands, alert-threshold defaults, event-category map, 18 Firestore
  collection names.
- `scripts/gen_contracts.py` generates TypeScript, Python and Dart bindings,
  with a `--check` mode that fails the build when any binding is stale.
- Risk banding (`0-25 LOW`, `26-50 MODERATE`, `51-75 HIGH`, `76-100 CRITICAL`)
  is implemented once per language from the same source and tested identically
  in all three.

**Backend (FastAPI)**

- Application factory with lifespan validation, CORS, security headers, and a
  request-context middleware that assigns and echoes `X-Request-ID`.
- Environment-driven settings (`backend/app/core/config.py`) with **no**
  hardcoded URLs or secrets, and `auto` resolution of the data, auth and
  storage adapters.
- Error taxonomy with a single JSON envelope
  (`{"error": {"code", "message", "details", "request_id"}}`) and handlers for
  application errors, validation failures, HTTP errors and unexpected
  exceptions. Internal details never reach the client; tracebacks are logged.
- Structured logging via structlog — console in development, JSON in
  staging/production, request id bound to the context.
- `GET /api/v1/health` reports the *resolved* adapter for each subsystem plus
  human-readable warnings for every degraded mode.
- Startup **fails** in production on the default JWT secret, a local adapter,
  or a wildcard CORS origin.

**Web dashboard (React 19 + TypeScript + Vite 8)**

- Design system in `web/src/styles/`: layered charcoal surfaces, single teal
  brand accent taken from the logo, the safety ramp reserved for risk
  semantics, 2-6px radii, 1px borders, compact 11-13px type scale, tabular
  numerals. Full light theme via token overrides, dark by default.
- Dashboard shell: collapsible navigation rail with role-grouped sections, top
  bar with live capability chips (demo mode, data backend, environment) and a
  theme toggle.
- Routing for all 12 dashboard sections with role-based visibility declared
  once in `web/src/app/navigation.ts`.
- Overview page wired to the real `/health` endpoint — every value shown comes
  from the API.
- Four-state UX contract enforced by `AsyncBoundary`: loading, error, empty,
  content. No data region can render blank.
- Typed API client with error-envelope decoding, Zod response validation,
  request-id propagation and a pluggable token provider.
- `PhasePendingPage` for unimplemented sections — states which phase delivers
  the feature and shows no invented metrics.
- Hand-drawn 16px icon set (37 glyphs) and inline-SVG brand mark; no icon
  library dependency.

**Mobile driver app (Flutter 3.41)**

- Android project, `com.trajyx` organisation, dark-only Material 3 theme
  mirroring the web tokens, 52px touch targets, tabular figures for live
  readouts.
- Six-destination bottom navigation (Home, Trip, Alerts, Safety, History,
  Profile).
- Home screen reaches the real API and reports platform state; shows the
  `DEMO DATA` chip when the backend has demo mode on.
- API client decoding the shared error envelope, distinguishing offline from
  server failure.
- Loading, empty and error views; `TrajyxMark` painted with `CustomPainter` so
  the brand is resolution-independent.
- Unimplemented tabs render an honest "not implemented yet" panel naming the
  phase.

**CV package**

- Coordinate conventions fixed and documented once: pixel origin top-left,
  `xyxy` boxes, angles in `[0, 360)` clockwise from image-up (matching compass
  bearing so image-space and GPS headings share one comparison function).
- `BoundingBox` with IoU, containment, clipping, and a `bottom_center`
  ground-contact reference point.
- `Detection`, `FrameMeta`, `TrackPoint`, `Track` — plain slotted dataclasses,
  sized for per-frame allocation rather than API validation.
- `Track` class assignment by majority vote, so one misread frame cannot change
  a vehicle's class.
- `Detector` and `Tracker` protocols with provenance types, so YOLO and
  ByteTrack are replaceable without touching downstream stages.
- COCO class mapping that deliberately returns `None` for classes the stock
  weights cannot distinguish (scooter, auto-rickshaw) rather than inventing a
  capability.

**ML package**

- Package structure for datasets, features, training, evaluation and
  inference, with the training/inference feature-parity rule documented at the
  package level.

**Firebase configuration**

- `firestore.rules` — deny by default; per-collection role rules; analysis
  output is `allow write: if false` for every client role; a user cannot change
  their own role.
- `storage.rules` — staff-only footage and evidence; drivers may write only
  images, only into their own folder, capped at 12 MiB; the 512 MiB video cap
  mirrors the backend setting.
- `firestore.indexes.json` — 15 composite indexes, each annotated with the
  query that requires it.
- `firebase.json` with emulator ports; service-account template with the real
  path gitignored.

**Documentation**

- `README.md`, `docs/architecture.md`, `docs/local-setup.md`,
  `docs/firebase-setup.md`, this file.
- `backend/.env.example` and `web/.env.example`, both fully commented.

### Tests run

All green, via `python scripts/verify.py`:

| Component | Check | Result |
|-----------|-------|--------|
| contracts | generated bindings current (`--check`) | PASS |
| backend | ruff lint (`backend cv ml scripts tests`) | PASS — 0 findings |
| backend | pytest | PASS — 10 tests |
| cv | pytest | PASS — 39 tests |
| web | oxlint | PASS — 0 warnings |
| web | tsc typecheck (strict) | PASS — 0 errors |
| web | vitest | PASS — 25 tests |
| web | production build | PASS |
| mobile | dart analyze | PASS — 0 issues |
| mobile | flutter test | PASS — 8 tests |

**Total: 82 automated tests, 10/10 checks passing.**

Test coverage worth noting:

- Risk banding verified at every documented boundary in all three languages.
- Navigation and router asserted to agree, so a section cannot be routable
  without a menu entry or vice versa.
- Role permissions asserted per role (operators excluded from analyst
  sections, drivers given no dashboard sections, settings admin-only).
- The four data states asserted against a stubbed network, including that the
  error envelope's code and message reach the screen.
- Placeholder pages asserted to state they are unimplemented.
- Bearing arithmetic verified across the 0/360 wrap point, the case a naive
  implementation gets wrong.
- Production configuration guards asserted to reject the default secret and
  local adapters.

### Manual verification

- API booted under uvicorn; `/`, `/api/v1/health`, `/api/v1/health/live`
  returned correct payloads; degraded-mode warnings present and accurate.
- Dashboard rendered at 1600×1000 via Playwright and inspected: live API
  values displayed, capability chips correct, no console errors.
- Both servers run together; the dashboard reads the backend over CORS.

### Bugs found and fixed during this phase

1. `structlog` configured with `WriteLoggerFactory` while using
   `add_logger_name`, which needs a stdlib logger — crashed every request.
   Switched to `stdlib.LoggerFactory` so uvicorn and structlog share one sink.
2. `average_bearing` returned `360.0` instead of `0.0` when averaging across
   north, because `% 360` on a tiny negative float yields `360.0`, outside the
   documented `[0, 360)` range. Added `normalize_bearing` with an epsilon
   guard; both bearing functions now use it.
3. Two React fast-refresh warnings from exporting hooks beside components.
   Split `theme-context.ts` and `page-meta-context.ts` out of their provider
   files.
4. TypeScript 6 deprecation of `baseUrl`, and Rollup 8 rejecting the object
   form of `manualChunks`. Switched to relative `paths` and a function.

### Known limitations

These are intentional at Phase 0, not defects:

- **No authentication.** The dashboard renders with a hardcoded `ADMIN` role
  (`PHASE_0_ROLE` in `web/src/app/routes.tsx`) so the shell and permission
  tables can be exercised. Phase 1 replaces it with a real session.
- **No persistence in use.** The repository layer and local document store are
  designed but not implemented; nothing is written to disk yet. Phase 1.
- **No CV implementation.** `Detector` and `Tracker` are protocols only. No
  YOLO weights, no video decoding, no tracking. Phases 4-5.
- **No risk engine, no map, no analytics, no reports.** Phases 8-11, 16.
- **Mobile shows no safety score.** There are no risk zones to compute one
  from. Phases 13-14.
- **Firebase rules are unverified against a live project.** They are written
  and syntactically reviewed but have not been deployed or exercised with the
  emulator. Phase 1.
- **`torch` is not installed.** `cv/requirements.txt` deliberately leaves it
  unpinned because the correct build depends on the target accelerator, and a
  wrong pin silently degrades to CPU inference.
- **The web bundle is a single 458 kB chunk.** The `manualChunks` splitting is
  configured but has nothing to split yet, since no page imports MapLibre,
  Recharts or Three.js.
- **Light theme is untested visually.** Tokens are defined and the toggle
  works; no screenshot review has been done.

### Next phase

**Phase 1 — Authentication, roles and database layer**

Planned scope:

- Repository interfaces plus both adapters: Firestore and local JSON store.
- Firebase Admin initialisation with token verification; local development
  token issuance as the fallback path.
- Four roles (`ADMIN`, `TRAFFIC_OPERATOR`, `ANALYST`, `DRIVER`) as custom
  claims, mirrored into user documents.
- FastAPI dependencies for authentication and role authorisation.
- `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me`, user management
  endpoints.
- Web auth context, login page, route guards, session persistence.
- Mobile login and session storage.
- Verification: login, logout, role restrictions enforced server-side (not
  only hidden in the UI), and database reads and writes through both adapters.
