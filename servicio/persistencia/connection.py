"""
Capa 3 · Persistencia · Database connection.

The only module that knows how to reach PostgreSQL. Every repository opens its
connection through `connect()`, so no other module ever handles the connection
string.

One connection is opened per unit of work and closed afterwards. The managed
database drops idle connections, and opening per unit of work keeps this layer
free of stale-connection handling. Should the cost ever matter, a pool can be
introduced here without touching a single repository.

Run a self-check with:

    python -m servicio.persistencia.connection
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg import rows, sql

from . import settings

# Tables created by schema/001_create_tables.sql, in dependency order.
TABLES = ("patient", "organ", "model", "study",
          "projection", "processing_stage", "lesion")


class DatabaseUnavailable(RuntimeError):
    """The database could not be reached."""


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Open a connection whose cursors return each row as a dictionary.

    The transaction is committed when the block finishes without error, and
    rolled back when it raises. The connection is always closed.
    """
    try:
        connection = psycopg.connect(
            settings.database_url(),
            row_factory=rows.dict_row,
            connect_timeout=10,
        )
    except psycopg.OperationalError as error:
        raise DatabaseUnavailable(
            "Could not reach the database. Check that the project is not paused "
            "and that DATABASE_URL points to the session pooler."
        ) from error

    try:
        with connection:
            yield connection
    finally:
        connection.close()


def row_counts() -> dict[str, int]:
    """Number of rows in each table. Also proves the schema was applied."""
    counts: dict[str, int] = {}
    with connect() as connection:
        for table in TABLES:
            query = sql.SQL("select count(*) as total from {}").format(
                sql.Identifier(table))
            counts[table] = connection.execute(query).fetchone()["total"]
    return counts


def _self_check() -> int:
    """Report whether this layer can reach the database. Prints no secret."""
    print("=" * 62)
    print("PERSISTENCE LAYER · DATABASE SELF-CHECK")
    print("=" * 62)

    try:
        for name in ("DATABASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_KEY"):
            getattr(settings, name.lower())()
            print(f"  {name:<22}: defined")
        print(f"  {'STORAGE_BUCKET':<22}: {settings.STORAGE_BUCKET}")
    except settings.MissingSetting as error:
        print(f"\n  FAILED: {error}")
        return 1

    try:
        with connect() as connection:
            version = connection.execute("select version()").fetchone()["version"]
        print(f"\n  server               : {version.split(',')[0]}")
    except DatabaseUnavailable as error:
        print(f"\n  FAILED: {error}")
        return 1

    counts = row_counts()
    print("\n  table                   rows")
    for table, total in counts.items():
        print(f"  {table:<22}{total:>6}")

    problems = []
    if counts["organ"] != 2:
        problems.append("the organ table should hold exactly 2 seed rows")
    if counts["patient"] < 1:
        problems.append("the placeholder patient PAC000000 is missing")

    print()
    if problems:
        for problem in problems:
            print(f"  FAILED: {problem}")
        print("\n  Re-run schema/001_create_tables.sql.")
        return 1

    print("  SELF-CHECK PASSED")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_check())