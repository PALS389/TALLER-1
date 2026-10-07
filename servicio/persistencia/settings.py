"""
Capa 3 · Persistencia · Settings.

Single place that reads the credentials this layer needs. Values live in a
`.env` file at the repository root, which is listed in `.gitignore` and is
never committed.

Nothing here ever prints or logs a secret: when a value is missing, only the
name of the variable is reported.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# <root>/servicio/persistencia/settings.py  ->  <root>
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(REPOSITORY_ROOT / ".env")

# Bucket that holds the binary files of every study.
STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "radvol3d")


class MissingSetting(RuntimeError):
    """A required environment variable is not defined."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"The environment variable {name} is not defined. Copy .env.example "
            f"to .env at the repository root and fill in the real values."
        )
        self.name = name


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value or not value.strip():
        raise MissingSetting(name)
    return value.strip()


def database_url() -> str:
    """Connection string of the PostgreSQL database."""
    return _required("DATABASE_URL")


def supabase_url() -> str:
    """Base URL of the managed project, with no trailing path.

    The dashboard shows this URL with `/rest/v1` appended on some screens.
    That suffix belongs to the REST API, not to the project, and the storage
    client appends its own path, so it is stripped here.
    """
    url = _required("SUPABASE_URL").rstrip("/")
    for suffix in ("/rest/v1", "/storage/v1"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url


def supabase_service_key() -> str:
    """Secret key used by the storage client. Never leaves the backend."""
    return _required("SUPABASE_SERVICE_KEY")