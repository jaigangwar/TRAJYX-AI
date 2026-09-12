# TRAJYX — development status

This file is the authoritative record of what is implemented, what is not, and
what was actually verified. It is updated at the end of every phase.

Anything not listed as complete below does not exist, regardless of how the
interface may look.

**Last updated:** Phase 1 completion
**Current phase:** 1 of 20 — complete
**Next phase:** 2 — Web dashboard foundation

## Verification summary

`python scripts/verify.py` — 9/9 checks pass.

| Component | Check | Result |
|-----------|-------|--------|
| contracts | generated bindings current | PASS |
| lint | ruff (backend, cv, ml, scripts, tests) | PASS — 0 findings |
| python | pytest | PASS — 153 tests |
| web | oxlint | PASS — 0 warnings |
| web | tsc typecheck (strict) | PASS — 0 errors |
| web | vitest | PASS — 44 tests |
| web | production build | PASS |
| mobile | dart analyze | PASS — 0 issues |
| mobile | flutter test | PASS — 19 tests |

**216 automated tests.** Plus a real-browser end-to-end sign-in check
(`web/scripts/e2e-login.mjs`, 7/7).

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
