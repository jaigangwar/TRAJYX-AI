"""Adapter selection and the Firebase Admin singleton.

This is the only module that knows both adapters exist. Everything else
depends on :class:`DocumentStore`.
"""

from __future__ import annotations

import json
import threading
from typing import Any

import structlog

from app.core.config import DataBackend, Settings, StorageBackend
from app.core.errors import DependencyUnavailableError
from app.repositories.base import DocumentStore
from app.repositories.local_store import LocalDocumentStore

log = structlog.get_logger(__name__)

_firebase_lock = threading.Lock()
_firebase_app: Any = None


def _credentials(settings: Settings) -> Any:
    """Build Firebase credentials from a file path or raw JSON."""
    from firebase_admin import credentials

    if settings.firebase_credentials_json:
        try:
            payload = json.loads(settings.firebase_credentials_json)
        except json.JSONDecodeError as error:
            raise DependencyUnavailableError(
                "TRAJYX_FIREBASE_CREDENTIALS_JSON is not valid JSON."
            ) from error
        return credentials.Certificate(payload)

    path = settings.firebase_credentials_path
    if path and path.is_file():
        return credentials.Certificate(str(path))

    raise DependencyUnavailableError(
        "Firebase credentials are not configured. Set TRAJYX_FIREBASE_CREDENTIALS_PATH "
        "or TRAJYX_FIREBASE_CREDENTIALS_JSON. See docs/firebase-setup.md."
    )


def get_firebase_app(settings: Settings) -> Any:
    """Initialise the Firebase Admin app once per process.

    Firebase Admin raises if initialised twice, and uvicorn's reloader plus
    test fixtures both make double initialisation easy, so the app is cached
    behind a lock and an existing app is reused.
    """
    global _firebase_app

    if _firebase_app is not None:
        return _firebase_app

    with _firebase_lock:
        if _firebase_app is not None:
            return _firebase_app

        import firebase_admin

        options: dict[str, Any] = {}
        if settings.firebase_project_id:
            options["projectId"] = settings.firebase_project_id
        if settings.firebase_storage_bucket:
            options["storageBucket"] = settings.firebase_storage_bucket

        try:
            _firebase_app = firebase_admin.initialize_app(_credentials(settings), options)
        except ValueError:
            # Already initialised elsewhere in this process (reloader, tests).
            _firebase_app = firebase_admin.get_app()

        log.info("firebase.initialised", project_id=settings.firebase_project_id)
        return _firebase_app


def reset_firebase_app() -> None:
    """Drop the cached app. For tests only."""
    global _firebase_app
    with _firebase_lock:
        _firebase_app = None


def create_document_store(settings: Settings) -> DocumentStore:
    """Build the document store the configuration selects."""
    backend = settings.resolved_data_backend

    if backend is DataBackend.FIRESTORE:
        from firebase_admin import firestore

        from app.repositories.firestore_store import FirestoreDocumentStore

        app = get_firebase_app(settings)
        client = firestore.client(app=app)
        log.info("repository.selected", backend="firestore", project_id=settings.firebase_project_id)
        return FirestoreDocumentStore(client, project_id=settings.firebase_project_id)

    log.warning(
        "repository.selected",
        backend="local",
        root=str(settings.local_data_dir),
        note="Development and demo use only.",
    )
    return LocalDocumentStore(settings.local_data_dir)


def create_storage_backend(settings: Settings) -> Any:
    """Build the object-storage adapter the configuration selects."""
    from app.services.storage import FirebaseObjectStorage, LocalObjectStorage

    if settings.resolved_storage_backend is StorageBackend.FIREBASE:
        from firebase_admin import storage as firebase_storage

        app = get_firebase_app(settings)
        bucket = firebase_storage.bucket(name=settings.firebase_storage_bucket, app=app)
        log.info("storage.selected", backend="firebase", bucket=settings.firebase_storage_bucket)
        return FirebaseObjectStorage(bucket)

    log.warning(
        "storage.selected",
        backend="local",
        root=str(settings.local_storage_dir),
        note="Development and demo use only.",
    )
    return LocalObjectStorage(settings.local_storage_dir)
