"""
Capa 3 · Persistencia · Object storage.

The only module that knows where the binary files of a study live. It speaks
in arrays and bytes; nobody above it ever sees a bucket, a key or an HTTP call.

Metadata goes to PostgreSQL, binaries go here, and the database keeps the path
that points at each one. Arrays travel in NumPy's own `.npy` format, which
carries the shape and the data type, so what comes back is identical to what
went in. Loading never unpickles, so a stored file cannot execute code.

Run a self-check with:

    python -m servicio.persistencia.storage
"""
from __future__ import annotations

import io
import time

import httpx
import numpy as np
from supabase import create_client

from . import settings

# Content types of the formats this project stores.
CONTENT_TYPES = {
    ".npy": "application/octet-stream",
    ".pth": "application/octet-stream",
    ".glb": "model/gltf-binary",
    ".png": "image/png",
    ".json": "application/json",
}
DEFAULT_CONTENT_TYPE = "application/octet-stream"


class StorageError(RuntimeError):
    """The object storage could not carry out the operation."""


class FileNotFoundInStorage(LookupError):
    """No object is stored under that path."""


def _content_type(path: str) -> str:
    for suffix, content_type in CONTENT_TYPES.items():
        if path.endswith(suffix):
            return content_type
    return DEFAULT_CONTENT_TYPE


def _check_path(path: str) -> str:
    """Reject anything that could reach outside the folder it names.

    The local store this replaces refused paths such as `../other`, and the
    same guarantee has to hold here: an identifier must never be able to build
    a path into another study's folder.
    """
    cleaned = path.strip().strip("/")
    if not cleaned or ".." in cleaned.split("/") or "\\" in cleaned:
        raise StorageError(f"Invalid storage path: {path!r}")
    return cleaned


def _looks_missing(error: Exception) -> bool:
    """Whether the storage service is reporting 'there is no such object'.

    The client raises one error class for every failure and carries the reason
    in its status and message, so both are inspected.
    """
    status = getattr(error, "status", None) or getattr(error, "statusCode", None)
    if str(status) == "404":
        return True
    message = str(error).lower()
    return "not found" in message or "does not exist" in message


class ObjectStorage:
    """Reads and writes the binary files of the studies.

    One client is built per instance and reused, because it holds the
    connection pool the HTTP calls go through.
    """

    def __init__(self, bucket: str | None = None) -> None:
        self._bucket_name = bucket or settings.STORAGE_BUCKET
        client = create_client(settings.supabase_url(),
                               settings.supabase_service_key())
        self._bucket = client.storage.from_(self._bucket_name)

    # ---------- bytes ----------
    def save_bytes(self, path: str, content: bytes) -> None:
        """Write the object, replacing it when it already exists."""
        key = _check_path(path)
        try:
            self._bucket.upload(
                path=key,
                file=content,
                file_options={"content-type": _content_type(key),
                              "upsert": "true"},
            )
        except Exception as error:
            raise StorageError(
                f"Could not write {key!r} to bucket {self._bucket_name!r}."
            ) from error

    def read_bytes(self, path: str) -> bytes:
        """Raw content of the object."""
        key = _check_path(path)
        for attempt in range(3):
            try:
                return self._bucket.download(key)
            except Exception as error:
                if isinstance(error, httpx.TransportError) and attempt < 2:
                    time.sleep(0.2 * (2 ** attempt))
                    continue
                if _looks_missing(error):
                    raise FileNotFoundInStorage(key) from error
                raise StorageError(
                    f"Could not read {key!r} from bucket {self._bucket_name!r}."
                ) from error
        raise StorageError("Storage read attempts exhausted.")

    # ---------- arrays ----------
    def save_array(self, path: str, array: np.ndarray) -> None:
        """Store the array in `.npy` format, shape and data type included."""
        buffer = io.BytesIO()
        np.save(buffer, array, allow_pickle=False)
        self.save_bytes(path, buffer.getvalue())

    def read_array(self, path: str) -> np.ndarray:
        """Read back an array stored with `save_array`."""
        content = self.read_bytes(path)
        try:
            return np.load(io.BytesIO(content), allow_pickle=False)
        except ValueError as error:
            raise StorageError(
                f"The object {path!r} is not a readable .npy file."
            ) from error

    # ---------- housekeeping ----------
    def exists(self, path: str) -> bool:
        """Whether an object is stored under that path."""
        key = _check_path(path)
        folder, _, name = key.rpartition("/")
        try:
            entries = self._bucket.list(folder)
        except Exception as error:
            raise StorageError(
                f"Could not list {folder or '/'!r} in bucket "
                f"{self._bucket_name!r}."
            ) from error
        return any(entry.get("name") == name for entry in entries)

    def remove(self, paths: list[str]) -> None:
        """Delete the named objects. Paths that hold nothing are ignored."""
        keys = [_check_path(path) for path in paths]
        if not keys:
            return
        try:
            self._bucket.remove(keys)
        except Exception as error:
            raise StorageError(
                f"Could not delete {keys} from bucket {self._bucket_name!r}."
            ) from error


def _self_check() -> int:
    """Write, read, overwrite and delete a throw-away object. Cleans up after itself."""
    print("=" * 62)
    print("PERSISTENCE LAYER · OBJECT STORAGE SELF-CHECK")
    print("=" * 62)

    storage = ObjectStorage()
    path = "SELFCHECK/array.npy"
    failures: list[str] = []
    print(f"  bucket               : {storage._bucket_name}")

    original = np.arange(24, dtype=np.float32).reshape(2, 3, 4) / 7.0
    storage.save_array(path, original)
    print(f"  wrote                : {path} {original.shape} {original.dtype}")

    if not storage.exists(path):
        failures.append("the object was written but exists() does not see it")

    recovered = storage.read_array(path)
    print(f"  read back            : {recovered.shape} {recovered.dtype}")
    if recovered.shape != original.shape or recovered.dtype != original.dtype:
        failures.append("the shape or the data type changed in transit")
    elif not np.array_equal(recovered, original):
        failures.append("the values changed in transit")

    raw = storage.read_bytes(path)
    if not raw.startswith(b"\x93NUMPY"):
        failures.append("the raw bytes are not a .npy file")
    print(f"  raw bytes            : {len(raw)} bytes, valid .npy header")

    # Re-processing a study overwrites its volume, so writing twice must work.
    replacement = np.ones((2, 2), dtype=np.float32)
    storage.save_array(path, replacement)
    if not np.array_equal(storage.read_array(path), replacement):
        failures.append("overwriting an existing object did not take effect")
    else:
        print("  overwrite            : replaced in place")

    try:
        storage.read_array("SELFCHECK/does-not-exist.npy")
        failures.append("reading a missing object did not raise")
    except FileNotFoundInStorage:
        print("  missing object       : raises FileNotFoundInStorage")

    try:
        storage.save_bytes("../escape.npy", b"x")
        failures.append("a path pointing outside its folder was accepted")
    except StorageError:
        print("  path '../escape.npy' : rejected, as it should be")

    storage.remove([path])
    if storage.exists(path):
        failures.append("the throw-away object was not deleted")
    else:
        print("  cleanup              : object removed")

    print()
    if failures:
        for failure in failures:
            print(f"  FAILED: {failure}")
        return 1
    print("  SELF-CHECK PASSED")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_check())
