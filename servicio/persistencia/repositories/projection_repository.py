"""
Capa 3 · Persistencia · Projection repository.

Reads and writes the `projection` table, which holds one row per radiograph:
the angle it was taken at, where its file is stored, and the name of the file
the user uploaded, which the interface shows back.

The rule that a study has exactly four projections, one per agreed angle,
belongs to the business layer and is enforced there. What the database
guarantees is narrower and complementary: an angle outside the agreed set is
refused, and the same angle cannot be stored twice within one study.

Run a self-check with:

    python -m servicio.persistencia.repositories.projection_repository
"""
from __future__ import annotations

from typing import NamedTuple, Sequence

from ..connection import connect


class ProjectionFile(NamedTuple):
    """One radiograph of a study, as this layer stores it."""

    angle_degrees: int
    file_path: str
    original_name: str


_SAVE = """
    insert into projection (study_code, angle_degrees, file_path, original_name)
    values (%(study_code)s, %(angle_degrees)s, %(file_path)s, %(original_name)s)
    on conflict (study_code, angle_degrees) do update set
        file_path     = excluded.file_path,
        original_name = excluded.original_name
"""


class ProjectionRepository:
    """Access to the `projection` table."""

    def save_all(self, study_code: str,
                 projections: Sequence[ProjectionFile]) -> None:
        """Store every projection of a study in a single transaction.

        A projection whose angle is already stored for that study is updated
        rather than duplicated, so re-registering a study replaces its files
        instead of failing.
        """
        if not projections:
            return
        rows = [{"study_code": study_code,
                 "angle_degrees": projection.angle_degrees,
                 "file_path": projection.file_path,
                 "original_name": projection.original_name}
                for projection in projections]
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(_SAVE, rows)

    def find_by_study(self, study_code: str) -> list[ProjectionFile]:
        """Projections of a study, ordered by angle. Empty when it has none."""
        with connect() as connection:
            rows = connection.execute(
                "select angle_degrees, file_path, original_name "
                "from projection where study_code = %s order by angle_degrees",
                (study_code,),
            ).fetchall()
        return [ProjectionFile(row["angle_degrees"], row["file_path"],
                               row["original_name"]) for row in rows]


def _self_check() -> int:
    """Store four projections against a throw-away study. Cleans up after itself."""
    from datetime import datetime

    import psycopg

    from .organ_repository import OrganRepository
    from .study_repository import StudyRepository, to_database_status

    print("=" * 62)
    print("PERSISTENCE LAYER · PROJECTION REPOSITORY SELF-CHECK")
    print("=" * 62)

    organs = OrganRepository()
    studies = StudyRepository()
    projections = ProjectionRepository()
    code = "SELFCHECK-PROJECTION"
    failures: list[str] = []

    studies.delete(code)
    studies.save(code, organs.find_id_by_name("pulmon"),
                 datetime.fromisoformat("2026-10-06T18:45:30"),
                 to_database_status("Pendiente"))

    # The four agreed angles, with the file names the interface would send.
    written = [
        ProjectionFile(0, f"{code}/projections/angle_000.npy", "ap.png"),
        ProjectionFile(45, f"{code}/projections/angle_045.npy", "oblicua.png"),
        ProjectionFile(90, f"{code}/projections/angle_090.npy", "lateral.png"),
        ProjectionFile(135, f"{code}/projections/angle_135.npy", "oblicua2.png"),
    ]
    projections.save_all(code, written)
    recovered = projections.find_by_study(code)
    print(f"  stored               : {len(recovered)} projections")
    for projection in recovered:
        print(f"    {projection.angle_degrees:>3}deg  {projection.original_name}")

    if recovered != written:
        failures.append("the projections did not come back as they were stored")
    if [p.angle_degrees for p in recovered] != [0, 45, 90, 135]:
        failures.append("the projections did not come back ordered by angle")

    # Re-registering a study replaces its files instead of duplicating them.
    projections.save_all(code, [ProjectionFile(
        0, f"{code}/projections/angle_000.npy", "ap-corregida.png")])
    again = projections.find_by_study(code)
    if len(again) != 4:
        failures.append(f"re-saving one angle left {len(again)} rows instead of 4")
    elif again[0].original_name != "ap-corregida.png":
        failures.append("re-saving an angle did not update its file name")
    else:
        print("  re-saving angle 0    : replaced, still 4 rows")

    # An angle outside the agreed set must be refused by the database.
    try:
        projections.save_all(code, [ProjectionFile(
            30, f"{code}/projections/angle_030.npy", "mala.png")])
        failures.append("an angle of 30 degrees was accepted")
    except psycopg.errors.CheckViolation:
        print("  angle of 30 degrees  : refused by the database")

    # Deleting the study cascades to its projections.
    studies.delete(code)
    if projections.find_by_study(code):
        failures.append("the projections outlived the study they belong to")
    else:
        print("  cleanup              : study and projections removed")

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