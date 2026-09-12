"""Object storage for video, evidence frames and generated reports.

Binary data never goes into the document store: a Firestore document is capped
at 1 MiB and billed per read, so storing a video there is both impossible and
wrong. Documents hold metadata plus a storage key; bytes live here.

Two adapters behind one interface, selected by ``TRAJYX_STORAGE_BACKEND``.
"""

from __future__ import annotations

import abc
import asyncio
import mimetypes
import shutil
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, BinaryIO

import structlog

from app.core.errors import NotFoundError, ValidationError

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Result of a successful upload."""

    key: str
    """Storage-relative path, e.g. ``videos/<job_id>/source.mp4``. This is what
    goes into the document, never a signed URL — those expire."""

    size_bytes: int
    content_type: str


class ObjectStorage(abc.ABC):
    """Binary object storage."""

    @abc.abstractmethod
    async def put(self, key: str, stream: BinaryIO, content_type: str) -> StoredObject:
        """Store a stream under ``key``, replacing anything already there."""

    @abc.abstractmethod
    async def put_bytes(self, key: str, data: bytes, content_type: str) -> StoredObject:
        """Store in-memory bytes. Used for snapshots and small exports."""

    @abc.abstractmethod
    async def get_bytes(self, key: str) -> bytes:
        """Read an object.

        Raises:
            NotFoundError: if the key does not exist.
        """

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """Remove an object. Deleting a missing key is not an error."""

    @abc.abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abc.abstractmethod
    async def signed_url(self, key: str, expires_in: timedelta = timedelta(hours=1)) -> str:
        """Time-limited read URL.

        Evidence frames and video are served to the dashboard this way rather
        than being made public: footage is the most sensitive data here, and a
        public URL cannot be revoked.
        """

    @abc.abstractmethod
    async def local_path(self, key: str) -> Path:
        """A filesystem path the analysis worker can open.

        OpenCV and PyAV need a real file. For local storage this is the stored
        file itself; for cloud storage the object is downloaded to a temporary
        file, so callers must not assume the path persists.
        """

    @abc.abstractmethod
    async def health(self) -> dict[str, Any]: ...


def validate_key(key: str) -> str:
    """Reject keys that could escape their prefix.

    Keys are assembled from ids and filenames, and a filename arrives from an
    upload. Traversal segments here would let an upload overwrite an unrelated
    object.
    """
    cleaned = key.strip().lstrip("/")
    if not cleaned:
        raise ValidationError("Storage key must not be empty.")
    parts = cleaned.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValidationError(f"Invalid storage key: {key!r}")
    if "\\" in cleaned or "\x00" in cleaned:
        raise ValidationError(f"Invalid storage key: {key!r}")
    return cleaned


class LocalObjectStorage(ObjectStorage):
    """Filesystem-backed storage for development and demos."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        path = (self._root / validate_key(key)).resolve()
        root = self._root.resolve()
        # Belt and braces: even with key validation, confirm containment.
        if not path.is_relative_to(root):
            raise ValidationError(f"Storage key escapes the storage root: {key!r}")
        return path

    async def put(self, key: str, stream: BinaryIO, content_type: str) -> StoredObject:
        path = self._resolve(key)

        def _write() -> int:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as handle:
                shutil.copyfileobj(stream, handle, length=1024 * 1024)
            return path.stat().st_size

        size = await asyncio.to_thread(_write)
        log.debug("storage.put", key=key, size_bytes=size, backend="local")
        return StoredObject(key=validate_key(key), size_bytes=size, content_type=content_type)

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> StoredObject:
        path = self._resolve(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(_write)
        return StoredObject(key=validate_key(key), size_bytes=len(data), content_type=content_type)

    async def get_bytes(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.is_file():
            raise NotFoundError(f"Stored object not found: {key}", details={"key": key})
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        await asyncio.to_thread(path.unlink, True)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._resolve(key).is_file)

    async def signed_url(self, key: str, expires_in: timedelta = timedelta(hours=1)) -> str:
        """Return an API path rather than a signed URL.

        Local storage has no signing authority, so objects are served through
        an authenticated API route. The expiry is therefore governed by the
        caller's session, not by the URL.
        """
        del expires_in
        if not await self.exists(key):
            raise NotFoundError(f"Stored object not found: {key}", details={"key": key})
        return f"/api/v1/storage/{validate_key(key)}"

    async def local_path(self, key: str) -> Path:
        path = self._resolve(key)
        if not path.is_file():
            raise NotFoundError(f"Stored object not found: {key}", details={"key": key})
        return path

    async def health(self) -> dict[str, Any]:
        import os

        return {
            "backend": "local",
            "root": str(self._root),
            "writable": os.access(self._root, os.W_OK),
            "note": "Local filesystem storage. Development and demo use only.",
        }


class FirebaseObjectStorage(ObjectStorage):
    """Firebase Cloud Storage adapter.

    The Admin SDK is blocking, so calls run in worker threads.
    """

    def __init__(self, bucket: Any) -> None:
        self._bucket = bucket

    async def put(self, key: str, stream: BinaryIO, content_type: str) -> StoredObject:
        safe_key = validate_key(key)

        def _upload() -> int:
            blob = self._bucket.blob(safe_key)
            blob.upload_from_file(stream, content_type=content_type)
            blob.reload()
            return int(blob.size or 0)

        size = await asyncio.to_thread(_upload)
        log.debug("storage.put", key=safe_key, size_bytes=size, backend="firebase")
        return StoredObject(key=safe_key, size_bytes=size, content_type=content_type)

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> StoredObject:
        safe_key = validate_key(key)

        def _upload() -> None:
            self._bucket.blob(safe_key).upload_from_string(data, content_type=content_type)

        await asyncio.to_thread(_upload)
        return StoredObject(key=safe_key, size_bytes=len(data), content_type=content_type)

    async def get_bytes(self, key: str) -> bytes:
        safe_key = validate_key(key)

        def _download() -> bytes:
            blob = self._bucket.blob(safe_key)
            if not blob.exists():
                raise NotFoundError(f"Stored object not found: {safe_key}", details={"key": safe_key})
            return bytes(blob.download_as_bytes())

        return await asyncio.to_thread(_download)

    async def delete(self, key: str) -> None:
        safe_key = validate_key(key)

        def _delete() -> None:
            blob = self._bucket.blob(safe_key)
            if blob.exists():
                blob.delete()

        await asyncio.to_thread(_delete)

    async def exists(self, key: str) -> bool:
        safe_key = validate_key(key)
        return await asyncio.to_thread(lambda: bool(self._bucket.blob(safe_key).exists()))

    async def signed_url(self, key: str, expires_in: timedelta = timedelta(hours=1)) -> str:
        safe_key = validate_key(key)

        def _sign() -> str:
            blob = self._bucket.blob(safe_key)
            if not blob.exists():
                raise NotFoundError(f"Stored object not found: {safe_key}", details={"key": safe_key})
            return str(blob.generate_signed_url(expiration=expires_in, method="GET", version="v4"))

        return await asyncio.to_thread(_sign)

    async def local_path(self, key: str) -> Path:
        """Download to a temporary file so the CV pipeline can open it.

        The caller owns the returned file and should delete it when finished;
        the analysis worker does this in a ``finally`` block.
        """
        import tempfile

        safe_key = validate_key(key)
        suffix = Path(safe_key).suffix or mimetypes.guess_extension("video/mp4") or ""

        def _download() -> Path:
            blob = self._bucket.blob(safe_key)
            if not blob.exists():
                raise NotFoundError(f"Stored object not found: {safe_key}", details={"key": safe_key})
            # delete=False and no context manager on purpose: the file must
            # outlive this function so the CV pipeline can open it. The caller
            # deletes it in a finally block.
            handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)  # noqa: SIM115
            try:
                blob.download_to_file(handle)
            finally:
                handle.close()
            return Path(handle.name)

        return await asyncio.to_thread(_download)

    async def health(self) -> dict[str, Any]:
        def _probe() -> dict[str, Any]:
            return {"backend": "firebase", "bucket": self._bucket.name, "reachable": self._bucket.exists()}

        try:
            return await asyncio.to_thread(_probe)
        except Exception as error:  # noqa: BLE001 - health must never raise
            log.warning("storage.health_check_failed", error=str(error))
            return {"backend": "firebase", "reachable": False, "error": str(error)}


# ------------------------------------------------------------------- key layout
# Centralised so the paths in firebase/storage.rules and the code that writes
# them cannot drift apart.


def video_key(job_id: str, filename: str) -> str:
    suffix = Path(filename).suffix.lower() or ".mp4"
    return f"videos/{job_id}/source{suffix}"


def processed_video_key(job_id: str) -> str:
    return f"processed/{job_id}/annotated.mp4"


def evidence_key(event_id: str, frame_index: int) -> str:
    return f"evidence/{event_id}/frame_{frame_index:06d}.jpg"


def report_image_key(user_id: str, report_id: str, suffix: str = ".jpg") -> str:
    return f"reports/{user_id}/{report_id}{suffix}"


def export_key(filename: str) -> str:
    return f"exports/{filename}"
