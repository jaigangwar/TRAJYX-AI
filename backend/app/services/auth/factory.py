"""Auth provider selection."""

from __future__ import annotations

import structlog

from app.core.config import AuthBackend, Settings
from app.repositories.base import DocumentStore
from app.services.auth.base import AuthProvider

log = structlog.get_logger(__name__)


def create_auth_provider(settings: Settings, store: DocumentStore) -> AuthProvider:
    """Build the identity provider the configuration selects."""
    if settings.resolved_auth_backend is AuthBackend.FIREBASE:
        from app.repositories.factory import get_firebase_app
        from app.services.auth.firebase_provider import FirebaseAuthProvider

        log.info("auth.selected", backend="firebase", project_id=settings.firebase_project_id)
        return FirebaseAuthProvider(store, settings, get_firebase_app(settings))

    from app.services.auth.local_provider import LocalAuthProvider

    log.warning(
        "auth.selected",
        backend="local",
        note="Self-issued development tokens. Not for production.",
    )
    return LocalAuthProvider(store, settings)
