"""Runtime configuration for the TRAJYX backend.

Every value is environment-driven; nothing about a deployment is hardcoded.
See backend/.env.example for the full documented surface.

Backend selection is deliberate rather than magical: `TRAJYX_DATA_BACKEND`
picks the persistence adapter and `TRAJYX_AUTH_BACKEND` picks the identity
provider. Both accept `auto`, which resolves to Firebase when credentials are
present and to the local adapter otherwise, so the stack runs end-to-end on a
clean checkout with no cloud project.
"""

from __future__ import annotations

import functools
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.password import MINIMUM_PRODUCTION_ROUNDS

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class DataBackend(str, Enum):
    """Persistence adapter for operational application data."""

    AUTO = "auto"
    FIRESTORE = "firestore"
    LOCAL = "local"


class AuthBackend(str, Enum):
    """Identity provider used to verify bearer tokens."""

    AUTO = "auto"
    FIREBASE = "firebase"
    LOCAL = "local"


class StorageBackend(str, Enum):
    """Object storage for videos, snapshots and generated reports."""

    AUTO = "auto"
    FIREBASE = "firebase"
    LOCAL = "local"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_prefix="TRAJYX_",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- service
    app_name: str = "TRAJYX API"
    app_version: str = "0.1.0"
    environment: Environment = Environment.DEVELOPMENT
    api_prefix: str = "/api/v1"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    log_json: bool = Field(
        default=False,
        description="Emit structured JSON logs. Enable in staging/production.",
    )

    # ------------------------------------------------------------------- CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Allowed browser origins for the web dashboard.",
    )

    # ------------------------------------------------------------- adapters
    data_backend: DataBackend = DataBackend.AUTO
    auth_backend: AuthBackend = AuthBackend.AUTO
    storage_backend: StorageBackend = StorageBackend.AUTO

    # ------------------------------------------------------------- firebase
    firebase_project_id: str | None = None
    firebase_credentials_path: Path | None = Field(
        default=None,
        description="Path to a service-account JSON file. Never commit this file.",
    )
    firebase_credentials_json: str | None = Field(
        default=None,
        description="Raw service-account JSON, for platforms that only expose env vars.",
    )
    firebase_storage_bucket: str | None = None

    # ------------------------------------------------------- local adapters
    local_data_dir: Path = Field(
        default=REPO_ROOT / "data" / "store",
        description="Root for the local JSON document store (development only).",
    )
    local_storage_dir: Path = Field(
        default=REPO_ROOT / "data" / "storage",
        description="Root for locally stored uploads and generated artifacts.",
    )

    # ---------------------------------------------------------------- security
    jwt_secret: str = Field(
        default="dev-only-insecure-secret-change-me",
        description=(
            "Signing key for locally issued development tokens. Required to be "
            "overridden outside development; startup fails otherwise."
        ),
    )
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_ttl_minutes: int = 60 * 12

    bcrypt_rounds: int = Field(
        default=12,
        ge=4,
        le=16,
        description=(
            "bcrypt work factor. 12 is roughly 250 ms per hash. Lowered only in "
            "the test environment, where the cost buys nothing and dominates "
            "the suite runtime; a floor is enforced everywhere else."
        ),
    )

    # ------------------------------------------------------------- uploads
    max_upload_bytes: int = Field(
        default=512 * 1024 * 1024,
        description="Hard cap on a single uploaded video (default 512 MiB).",
    )
    allowed_video_extensions: list[str] = Field(
        default=[".mp4", ".mov", ".avi", ".mkv", ".webm"],
    )
    allowed_video_content_types: list[str] = Field(
        default=[
            "video/mp4",
            "video/quicktime",
            "video/x-msvideo",
            "video/x-matroska",
            "video/webm",
        ],
    )

    # ------------------------------------------------------------ processing
    worker_concurrency: int = Field(
        default=1,
        description="In-process analysis workers. Raise only with GPU capacity.",
    )
    frame_stride: int = Field(
        default=2,
        description="Process every Nth frame. Trades temporal resolution for speed.",
    )

    # ------------------------------------------------------------------ demo
    demo_mode: bool = Field(
        default=True,
        description=(
            "Expose demo/simulation endpoints and seeded synthetic records. "
            "Synthetic records always carry origin=DEMO and are labeled in the UI."
        ),
    )

    # ------------------------------------------------------------- retention
    retention_days_detections: int = 30
    retention_days_events: int = 365

    @field_validator("cors_origins", "allowed_video_extensions", "allowed_video_content_types", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept both JSON arrays and plain comma-separated env values."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return value
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return upper

    # ------------------------------------------------------------ derived
    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def firebase_configured(self) -> bool:
        """True when enough Firebase configuration exists to initialise the SDK."""
        if self.firebase_credentials_json:
            return True
        path = self.firebase_credentials_path
        return bool(path and Path(path).is_file())

    @property
    def resolved_data_backend(self) -> DataBackend:
        if self.data_backend is not DataBackend.AUTO:
            return self.data_backend
        return DataBackend.FIRESTORE if self.firebase_configured else DataBackend.LOCAL

    @property
    def resolved_auth_backend(self) -> AuthBackend:
        if self.auth_backend is not AuthBackend.AUTO:
            return self.auth_backend
        return AuthBackend.FIREBASE if self.firebase_configured else AuthBackend.LOCAL

    @property
    def resolved_storage_backend(self) -> StorageBackend:
        if self.storage_backend is not StorageBackend.AUTO:
            return self.storage_backend
        if self.firebase_configured and self.firebase_storage_bucket:
            return StorageBackend.FIREBASE
        return StorageBackend.LOCAL

    def startup_warnings(self) -> list[str]:
        """Non-fatal configuration notes surfaced in logs and on /health."""
        notes: list[str] = []
        if self.resolved_data_backend is DataBackend.LOCAL:
            notes.append(
                "Data backend is LOCAL (on-disk JSON store). Suitable for development "
                "and demos only; configure Firebase for shared or persistent use."
            )
        if self.resolved_auth_backend is AuthBackend.LOCAL:
            notes.append(
                "Auth backend is LOCAL (self-issued development tokens). Configure "
                "Firebase Authentication before any real deployment."
            )
        if self.resolved_storage_backend is StorageBackend.LOCAL:
            notes.append("Object storage is LOCAL disk. Configure Firebase Storage for shared use.")
        if self.demo_mode:
            notes.append("DEMO MODE is enabled. Synthetic records are labeled origin=DEMO.")
        return notes

    def startup_errors(self) -> list[str]:
        """Fatal misconfigurations. Startup aborts when this is non-empty."""
        errors: list[str] = []
        if self.is_production:
            if self.jwt_secret == "dev-only-insecure-secret-change-me":
                errors.append("TRAJYX_JWT_SECRET must be set to a strong unique value in production.")
            if self.resolved_auth_backend is AuthBackend.LOCAL:
                errors.append("Local auth backend is not permitted in production. Configure Firebase.")
            if self.resolved_data_backend is DataBackend.LOCAL:
                errors.append("Local data backend is not permitted in production. Configure Firestore.")
            if "*" in self.cors_origins:
                errors.append("Wildcard CORS origin is not permitted in production.")
        if self.environment is not Environment.TEST and self.bcrypt_rounds < MINIMUM_PRODUCTION_ROUNDS:
            errors.append(
                f"TRAJYX_BCRYPT_ROUNDS must be at least {MINIMUM_PRODUCTION_ROUNDS} outside tests "
                f"(got {self.bcrypt_rounds})."
            )
        if self.frame_stride < 1:
            errors.append("TRAJYX_FRAME_STRIDE must be >= 1.")
        if self.max_upload_bytes <= 0:
            errors.append("TRAJYX_MAX_UPLOAD_BYTES must be positive.")
        return errors


@functools.lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton. Cached so env parsing happens once."""
    return Settings()
