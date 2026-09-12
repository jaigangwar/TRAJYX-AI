<div align="center">

<img src="assets/brand/trajyx-wordmark.png" alt="TRAJYX" width="620">

**Predictive Road Safety & Traffic Intelligence**

*Safer roads, brighter tomorrows.*

</div>

---

## What TRAJYX is

Conventional traffic systems **detect violations after they happen**.

TRAJYX **understands road behaviour, predicts risky situations, and warns
drivers before they reach a dangerous place.**

It observes traffic through CCTV or uploaded footage, tracks every road user
across frames, turns those tracks into trajectories and behaviour, converts
behaviour into explainable risk scores for road segments and times of day, and
pushes those scores to a driver application that warns ahead of the hazard —
not after it.

```
OBSERVE  ->  TRACK  ->  UNDERSTAND  ->  PREDICT  ->  WARN  ->  LEARN
```

## Current state

**Phase 0 of 20 complete.** The foundation is built and verified: monorepo,
shared domain contract with generated bindings for three languages, a running
FastAPI backend with pluggable persistence, a React dashboard with its design
system, a Flutter driver app, and the CV/ML package interfaces.

No detection, tracking or risk analysis exists yet — those are phases 4 to 9.
The dashboard and mobile app show real data from the API and say plainly, on
each unimplemented section, which phase delivers it. Nothing is mocked to look
finished.

[**DEVELOPMENT_STATUS.md**](DEVELOPMENT_STATUS.md) is the authoritative record
of what works, what does not, and what was actually tested.

## Quick start

Runs with **no cloud account**. Firebase is optional.

```bash
# 1. Python environment
py -3.10 -m venv .venv                                   # Windows
.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
.venv/Scripts/python -m pip install -e shared/python -e cv -e ml

# 2. Backend
cp backend/.env.example backend/.env
python scripts/dev_api.py                                # -> http://127.0.0.1:8000/docs

# 3. Dashboard
cd web && npm install && cp .env.example .env && npm run dev
                                                         # -> http://localhost:5173
```

Full instructions, including the mobile app: [docs/local-setup.md](docs/local-setup.md)

Verify the whole repository at any time:

```bash
python scripts/verify.py
```

## Architecture at a glance

```
                       ┌─────────────────────────┐
   CCTV / uploaded ───► │  Analysis worker        │
   video                │  (cv/ + ml/)            │
                       └───────────┬─────────────┘
                                   │ detections, tracks, events, risk
                                   ▼
┌──────────────┐          ┌────────────────────┐         ┌──────────────────┐
│ Web dashboard│ ◄──────► │  FastAPI backend   │ ◄─────► │  Firestore       │
│ (web/)       │   REST   │  (backend/)        │ adapter │  or local store  │
└──────────────┘          │  risk · geo · alert│         └──────────────────┘
┌──────────────┐          │       engines      │         ┌──────────────────┐
│ Driver app   │ ◄──────► │                    │ ◄─────► │  Object storage  │
│ (mobile/)    │   REST   └────────────────────┘ adapter │  Firebase/local  │
└──────────────┘                                         └──────────────────┘
```

Both clients consume the same backend, so the logic that warns a driver is the
same logic that explains a hotspot to an operator.

Detail: [docs/architecture.md](docs/architecture.md)

## Technology

| Layer | Choice | Why |
|-------|--------|-----|
| Web | React 19, TypeScript, Vite, Tailwind v4 | Dense operations UI, strict types |
| Maps | MapLibre GL | Production GIS rendering with no mandatory API key |
| Charts | Recharts | Composable, no chart-library lock-in |
| 3D | Three.js | Used only where 3D adds meaning (phase 12) |
| Backend | FastAPI, Pydantic v2 | Typed async API, generated OpenAPI |
| CV | OpenCV, Ultralytics YOLO, ByteTrack | Behind swappable interfaces |
| ML | scikit-learn, XGBoost | Small tabular feature set; explainable per prediction |
| Data | Firebase Auth / Firestore / Storage | With a local fallback and a PostGIS migration path |
| Mobile | Flutter, Riverpod | Android first, iOS-ready structure |

## Repository layout

```
trajyx/
├── backend/     FastAPI service — API, risk engine, geo engine, workers
├── web/         React + TypeScript dashboard
├── mobile/      Flutter driver application
├── cv/          Detection, tracking, trajectory, conflict analysis
├── ml/          Risk-model features, training, evaluation, inference
├── shared/      Canonical domain contract + generated bindings
├── firebase/    Firestore rules, indexes, Storage rules
├── scripts/     Contract generation, dev servers, verification
├── tests/       Backend, CV, geo, risk, integration
├── docs/        Architecture, setup, API, pipelines
├── models/      Weights and evaluation artifacts (gitignored)
└── datasets/    Training and sample data (gitignored)
```

## The data honesty contract

TRAJYX is a safety system, so presenting a guess as a measurement is its worst
possible failure. Three rules are enforced in the type system, not left to
reviewer discipline:

1. **Every record carries an origin** — `MEASURED`, `ESTIMATED` or `DEMO`. The
   interface shows a chip for the latter two; the *absence* of a chip means the
   value was measured.
2. **Visual checks are tri-state** — `DETECTED`, `NOT_DETECTED`,
   `UNABLE_TO_DETERMINE`. A helmet that cannot be seen is not an absent helmet.
3. **No metric is written by hand.** Precision, recall and F1 come only from a
   recorded evaluation run. There is no code path that writes a performance
   number from a literal.

It follows that speed is estimated only where camera calibration supports it,
time-to-collision is always labelled an estimate, and red-light violations are
suppressed entirely when signal phase is unknown.

## Privacy by design

No face recognition. No licence-plate reading. Track identifiers are anonymous
per-video counters, never reused across videos or correlated between cameras.
Drivers can read aggregate risk zones, never footage-derived detail about
individual road users. Retention is configurable per data class.

## Development phases

Built in order; each phase is verifiable on its own and none depends on a later
one.

| | Phase | | | Phase | |
|---|---|---|---|---|---|
| 0 | Foundation & monorepo | ✅ | 11 | Analytics | ⬜ |
| 1 | Auth & database | ⬜ | 12 | 3D visualisation | ⬜ |
| 2 | Dashboard foundation | ⬜ | 13 | Mobile driver app | ⬜ |
| 3 | Video upload & jobs | ⬜ | 14 | GPS & smart alerts | ⬜ |
| 4 | YOLO detection | ⬜ | 15 | Hazard reporting | ⬜ |
| 5 | Object tracking | ⬜ | 16 | Reports & export | ⬜ |
| 6 | Safety detection | ⬜ | 17 | Demo mode | ⬜ |
| 7 | Trajectory & interaction | ⬜ | 18 | Testing | ⬜ |
| 8 | Near-miss & risk engine | ⬜ | 19 | Hardening | ⬜ |
| 9 | ML risk model | ⬜ | 20 | Documentation | ⬜ |
| 10 | GIS risk map | ⬜ | | | |

## Documentation

| Document | Contents |
|----------|----------|
| [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) | What works, what does not, what was tested |
| [docs/architecture.md](docs/architecture.md) | System design, adapters, conventions |
| [docs/local-setup.md](docs/local-setup.md) | Running everything locally |
| [docs/firebase-setup.md](docs/firebase-setup.md) | Optional cloud configuration |

## Security

Never commit `firebase/service-account.json` or any `.env` file — both are
gitignored. Firebase *web* config values are public by design and safe in
`web/.env`; a service-account key is not. The backend refuses to start in
production with the default JWT secret, a local adapter, or a wildcard CORS
origin.

## License

Not yet licensed. All rights reserved by the authors.
