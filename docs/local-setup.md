# Local setup

TRAJYX runs end to end with **no cloud account**. Firebase is optional; without
it the backend uses an on-disk store, local development tokens and local file
storage, and says so on `/api/v1/health` and in the dashboard chrome.

## Prerequisites

| Tool | Version used | Needed for |
|------|--------------|-----------|
| Python | 3.10 or 3.11 | backend, CV, ML |
| Node.js | 20 or newer | web dashboard |
| Flutter | 3.35 or newer | mobile app |
| Git | any recent | version control |

Python 3.10 is recommended over 3.13+ because the CV stack (`torch`,
`ultralytics`, `opencv`) publishes wheels for it reliably. The backend alone
works on any supported version.

Optional:

- **Firebase CLI** (`npm i -g firebase-tools`) — only to deploy rules or run
  the emulator suite.
- **Android Studio** or an Android device — only for the mobile app.

## 1. Clone and create the Python environment

```bash
git clone https://github.com/jaigangwar/TRAJYX-AI.git
cd TRAJYX-AI

# Windows
py -3.10 -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip

# macOS / Linux
python3.10 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
```

All commands below use `.venv/Scripts/python` (Windows). On macOS and Linux use
`.venv/bin/python`.

## 2. Install Python dependencies

```bash
# API service plus dev tooling
.venv/Scripts/python -m pip install -r backend/requirements-dev.txt

# Shared contract, CV and ML packages, installed editable
.venv/Scripts/python -m pip install -e shared/python -e cv -e ml
```

The CV and ML *runtime* stacks are separate, because the API does not need
`torch`:

```bash
# Only on machines that run analysis. Install torch first — see cv/requirements.txt.
.venv/Scripts/python -m pip install -r cv/requirements.txt
.venv/Scripts/python -m pip install -r ml/requirements.txt
```

## 3. Configure the backend

```bash
cp backend/.env.example backend/.env
```

The defaults work as-is for local development. To generate a real signing key:

```bash
.venv/Scripts/python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 4. Start the API

```bash
python scripts/dev_api.py
```

- API: <http://127.0.0.1:8000>
- Interactive docs: <http://127.0.0.1:8000/docs>
- Health and resolved capabilities: <http://127.0.0.1:8000/api/v1/health>

Confirm the capability report says what you expect:

```bash
curl -s http://127.0.0.1:8000/api/v1/health
```

With no Firebase configured you should see `"data_backend": "local"` and four
warnings explaining the degraded modes. That is correct, not a failure.

## 5. Start the web dashboard

```bash
cd web
npm install
cp .env.example .env
npm run dev
```

Dashboard: <http://localhost:5173>

`web/.env` only needs changing if the API is not on `127.0.0.1:8000`.

## 6. Run the mobile app (optional)

```bash
cd mobile
flutter pub get
flutter devices          # confirm an emulator or device is attached
flutter run --dart-define=TRAJYX_API_BASE_URL=http://10.0.2.2:8000
```

`10.0.2.2` is how the Android emulator reaches the host machine. On a physical
device use the host's LAN address (`http://192.168.x.x:8000`) and make sure the
API is bound to `0.0.0.0`:

```bash
python scripts/dev_api.py --host 0.0.0.0
```

## 7. Verify everything

```bash
python scripts/verify.py
```

This runs contract-freshness, Python lint, backend tests, CV tests, web lint,
typecheck, tests and production build, plus Flutter analyze and tests — and
prints one summary. Components whose toolchain is missing are reported as
`SKIP`, not `FAIL`.

Subsets:

```bash
python scripts/verify.py --only web
python scripts/verify.py --only backend --only cv
python scripts/verify.py --list
```

## 8. Optional: connect Firebase

See [firebase-setup.md](firebase-setup.md). In short: create a project, enable
Email/Password auth, Firestore and Storage, download a service-account key to
`firebase/service-account.json`, then set in `backend/.env`:

```env
TRAJYX_FIREBASE_PROJECT_ID=your-project-id
TRAJYX_FIREBASE_CREDENTIALS_PATH=firebase/service-account.json
TRAJYX_FIREBASE_STORAGE_BUCKET=your-project-id.appspot.com
```

Restart the API; `/api/v1/health` should now report `firestore` and `firebase`,
and the dashboard chip changes from "Local store" to "Firestore".

## Troubleshooting

**`ModuleNotFoundError: trajyx_shared`**
The shared package is not installed. Run
`.venv/Scripts/python -m pip install -e shared/python`.

**Dashboard shows "Cannot reach the TRAJYX API"**
The API is not running, or `VITE_API_BASE_URL` in `web/.env` points elsewhere.
Check `curl http://127.0.0.1:8000/api/v1/health`.

**`Stale generated contracts`**
`shared/contracts/domain.json` changed without regenerating. Run
`python scripts/gen_contracts.py`.

**Startup fails with "Invalid configuration"**
Expected when `TRAJYX_ENVIRONMENT=production` while a local adapter or the
default JWT secret is in use. The message lists exactly what to fix.

**Port 5173 or 8000 already in use**
`python scripts/dev_api.py --port 8001`, and for the web app change `port` in
`web/vite.config.ts` (`strictPort` is on deliberately, so a silent port change
cannot break the API origin).

**Flutter: `shared_preferences_windows` warnings**
Only appears if desktop platforms are added to an Android-only project. Not
applicable to the current configuration.
