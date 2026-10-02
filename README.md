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

**Phases 0–8, 10–12 and 16 are complete.** The repository includes the video
analysis pipeline, explainable risk engine, GIS alerts, analytics, calibrated
3D conflict replay, reports, role-based dashboard and secure driver-app
foundation. See
[**DEVELOPMENT_STATUS.md**](DEVELOPMENT_STATUS.md) for the verified state.

The dashboard has 13 sections, including a new interactive junction
simulation. That screen is an explicitly labelled visual demo: its moving
tracks and proximity score are synthetic and are not CCTV measurements. The
other dashboard pages read from the API and preserve the `MEASURED`,
`ESTIMATED` and `DEMO` distinction.

**Still needed for an end-to-end deployment:** labelled real-world data and an
evaluated ML model, driver-facing mobile features, Firebase project
configuration, production hardening and the remaining technical/demo
documentation. The simulation helps present the workflow while those
separate items are built; it does not replace them. See
[**REMAINING.md**](REMAINING.md) for the work and its dependencies.

The last recorded full baseline is **341 automated tests** and **9/9
verification checks**, plus real-browser checks for sign-in, page rendering
and report export. The current web build passes; automated tests were not
rerun for the latest changes. Python workflow checks are pending because the
configured Python runtime is unavailable in the current environment.

## Quick start

Runs with **no cloud account**. Firebase is optional.

```bash
# 1. Python environment
py -3.10 -m venv .venv                                   # Windows
.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
.venv/Scripts/python -m pip install -e shared/python -e cv -e ml

# 2. Backend
cp backend/.env.example backend/.env
python scripts/seed_admin.py                             # creates the first admin
python scripts/dev_api.py                                # -> http://127.0.0.1:8000/docs

# 3. Dashboard  (new terminal)
cd web && npm install && cp .env.example .env && npm run dev
                                                         # -> http://localhost:5173

# 4. Optional: demo data, so the map and analytics have something to show
python scripts/seed_demo.py                              # every record tagged origin=DEMO
```

`seed_admin.py` prints the credentials it creates; sign in with those. Without
step 2 there is no account to sign in with, and without step 4 the Risk Map and
Analytics pages will correctly report that nothing has been measured yet.

Demo records are labelled `origin=DEMO` end to end — badge in the UI, a
disclosure banner on Analytics, and a warning line in every CSV export.
`python scripts/seed_demo.py --purge` removes them and touches nothing else.

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
| Charts | Hand-rolled SVG | Dense console charts; a null value must render as a gap, not a zero |
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
| 0 | Foundation & monorepo | ✅ | 11 | Analytics | ✅ |
| 1 | Auth & database | ✅ | 12 | 3D visualisation | ✅ |
| 2 | Dashboard foundation | ✅ | 13 | Mobile driver app | ⬜ |
| 3 | Video upload & jobs | ✅ | 14 | GPS & smart alerts | ⬜ |
| 4 | YOLO detection | ✅ | 15 | Hazard reporting | ⬜ |
| 5 | Object tracking | ✅ | 16 | Reports & export | ✅ |
| 6 | Safety detection | ✅ | 17 | Demo mode | ⬜* |
| 7 | Trajectory & interaction | ✅ | 18 | Testing | ⬜ |
| 8 | Near-miss & risk engine | ✅ | 19 | Hardening | ⬜ |
| 9 | ML risk model | ⬜ | 20 | Documentation | ⬜ |
| 10 | GIS risk map | ✅ | | | |

*The interactive simulation is a presentation prototype for phase 17. Full
demo mode (seeded data across the API, dashboard and exports) remains tracked
separately in [REMAINING.md](REMAINING.md).

## Documentation

| Document | Contents |
|----------|----------|
| [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) | What works, what does not, what was tested |
| [REMAINING.md](REMAINING.md) | What is left to build, and how to build it |
| [docs/ml-training.md](docs/ml-training.md) | Labelled data contract and reproducible ML train/evaluate commands |
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
