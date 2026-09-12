# Firebase setup

Firebase is **optional**. TRAJYX runs fully locally without it (see
[local-setup.md](local-setup.md)). Connect it when you need shared data,
multiple users, or a deployment.

## What Firebase provides

| Service | Used for |
|---------|----------|
| Authentication | User identity; roles as a custom claim |
| Firestore | Operational data: users, cameras, jobs, events, alerts |
| Cloud Storage | Uploaded video, annotated output, evidence frames, exports |

Heavy analytics and geospatial queries are designed to migrate to
PostgreSQL + PostGIS later — see
[architecture.md](architecture.md#migration-path-to-postgresql--postgis).

## 1. Create the project

1. <https://console.firebase.google.com> → **Add project**.
2. Name it (for example `trajyx-dev`). Google Analytics is not needed.

## 2. Enable Authentication

1. **Build → Authentication → Get started**.
2. Enable **Email/Password**.

TRAJYX uses email/password because operators are provisioned by an
administrator rather than self-registering. Other providers can be added
without backend changes; role assignment is unaffected because the role lives
in a custom claim, not in the provider.

## 3. Create the Firestore database

1. **Build → Firestore Database → Create database**.
2. Start in **production mode** — the rules in this repository are the real
   ones, and test mode would leave the database world-writable.
3. Pick a region close to your users. This cannot be changed later.

## 4. Enable Cloud Storage

1. **Build → Storage → Get started**, production mode.
2. Note the bucket name, usually `your-project-id.appspot.com`.

## 5. Get the web app config

1. **Project settings → General → Your apps → Add app → Web**.
2. Copy the config values into `web/.env`:

```env
VITE_FIREBASE_API_KEY=AIza...
VITE_FIREBASE_AUTH_DOMAIN=your-project-id.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your-project-id
VITE_FIREBASE_STORAGE_BUCKET=your-project-id.appspot.com
VITE_FIREBASE_APP_ID=1:123456789:web:abc123
```

These are **public by design** — they identify the project, they do not
authorise anything. Security comes from the Firestore and Storage rules. A
service-account key is a completely different thing and must never appear in
`web/.env`.

## 6. Get the service-account key (backend)

1. **Project settings → Service accounts → Generate new private key**.
2. Save it as `firebase/service-account.json`.

That path is gitignored. The file grants full administrative access to your
project and bypasses all security rules — treat it like a root password. If it
is ever committed or shared, revoke it immediately in the same console screen.

Then in `backend/.env`:

```env
TRAJYX_FIREBASE_PROJECT_ID=your-project-id
TRAJYX_FIREBASE_CREDENTIALS_PATH=firebase/service-account.json
TRAJYX_FIREBASE_STORAGE_BUCKET=your-project-id.appspot.com
```

On a platform that only exposes environment variables, use
`TRAJYX_FIREBASE_CREDENTIALS_JSON` with the file's contents instead.

## 7. Deploy rules and indexes

```bash
npm install -g firebase-tools
firebase login
firebase use --add          # select your project
firebase deploy --only firestore:rules,firestore:indexes,storage
```

The rules in `firebase/firestore.rules` deny by default and allow only what
each role genuinely needs. Two properties are worth knowing:

- **Clients never write analysis output.** Detections, tracking events,
  violations, near misses, risk events and model versions are `allow write: if
  false`. The backend writes them through the Admin SDK, which bypasses rules.
  Without this, a modified driver app could fabricate a violation.
- **A user cannot change their own role.** The role is a custom claim set by
  the backend, and the rules additionally reject any update to the `role` field
  on a user document.

Composite indexes in `firebase/firestore.indexes.json` are required: Firestore
rejects the dashboard's filtered and ordered queries without them.

## 8. Verify

Restart the API and check the capability report:

```bash
curl -s http://127.0.0.1:8000/api/v1/health
```

Expect `"data_backend": "firestore"`, `"auth_backend": "firebase"`,
`"storage_backend": "firebase"`, and no degraded-mode warnings. The dashboard
chip changes from **Local store** to **Firestore**.

## Using the emulator suite instead

For development against Firebase semantics without touching a real project:

```bash
firebase emulators:start
```

Ports are configured in `firebase.json`: Auth 9099, Firestore 8080,
Storage 9199, UI 4000.

## Security checklist

- [ ] `firebase/service-account.json` is not committed (`git status` shows it
      as ignored).
- [ ] Firestore and Storage were created in **production mode**.
- [ ] Rules and indexes are deployed, not just present in the repository.
- [ ] `TRAJYX_JWT_SECRET` is a generated value, not the shipped default.
- [ ] `TRAJYX_CORS_ORIGINS` lists only your real dashboard origins.
- [ ] The first administrator was created deliberately; no self-registration
      path grants `ADMIN`.
