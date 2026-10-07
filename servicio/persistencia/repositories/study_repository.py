"""
Capa 3 · Persistencia · Study repository.

Reads and writes the `study` table, which holds one row per set of radiographs
that the system processes.

Two translations live here, because both concern columns of this table:

  * Status. The database keeps a canonical vocabulary of four values, the one
    the entity-relationship model defines. The business layer uses its own
    wording, which is what the interface shows. Neither has to adopt the
    other's, so this module converts between them in both directions.

  * Patient. The web interface does not collect patient data yet, so a study
    arrives without one. Until it does, every study is linked to the
    placeholder patient created by the schema.

Numeric columns come back from the driver as decimals. They are converted to
floats here so that the values returned match the ones the business layer
wrote, and so they can be serialised as JSON further up.

Run a self-check with:

    python -m servicio.persistencia.repositories.study_repository
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ..connection import connect

# Patient every study is linked to while the interface collects no patient data.
PLACEHOLDER_PATIENT_CODE = "PAC000000"

# Canonical vocabulary of study.status <-> wording used by the business layer.
STATUS_TO_BUSINESS = {
    "pendiente":  "Pendiente",
    "procesando": "Procesando",
    "completado": "Reconstrucción completada",
    "error":      "Error",
}
STATUS_TO_DATABASE = {business: database
                      for database, business in STATUS_TO_BUSINESS.items()}

# Columns whose decimal values are handed back as floats.
_NUMERIC_COLUMNS = ("psnr", "ssim", "dice", "total_time_sec",
                    "volume_min", "volume_max", "volume_mean")

_SAVE = """
    insert into study (study_code, patient_code, organ_id, date_time, status,
                       total_time_sec, volume_min, volume_max, volume_mean)
    values (%(study_code)s, %(patient_code)s, %(organ_id)s, %(date_time)s,
            %(status)s, %(total_time_sec)s, %(volume_min)s, %(volume_max)s,
            %(volume_mean)s)
    on conflict (study_code) do update set
        patient_code   = excluded.patient_code,
        organ_id       = excluded.organ_id,
        date_time      = excluded.date_time,
        status         = excluded.status,
        total_time_sec = excluded.total_time_sec,
        volume_min     = excluded.volume_min,
        volume_max     = excluded.volume_max,
        volume_mean    = excluded.volume_mean
"""


class UnknownStatus(ValueError):
    """A status arrived that neither vocabulary defines."""


def to_database_status(business_status: str) -> str:
    """Translate the wording of the business layer into the stored value."""
    try:
        return STATUS_TO_DATABASE[business_status]
    except KeyError:
        known = ", ".join(repr(value) for value in STATUS_TO_DATABASE)
        raise UnknownStatus(
            f"Unknown status {business_status!r}. Known statuses: {known}. "
            f"Add it to STATUS_TO_BUSINESS and to the check constraint on "
            f"study.status before using it."
        ) from None


def to_business_status(database_status: str) -> str:
    """Translate the stored value back into the wording of the business layer."""
    try:
        return STATUS_TO_BUSINESS[database_status]
    except KeyError:
        raise UnknownStatus(
            f"The database holds the status {database_status!r}, which this "
            f"module does not know how to translate."
        ) from None


def _with_floats(row: dict) -> dict:
    """Same row, with its decimal values turned into floats."""
    return {key: float(value) if isinstance(value, Decimal) else value
            for key, value in row.items()}


class StudyRepository:
    """Access to the `study` table.

    Quality metrics (psnr, ssim, dice) belong to validation runs that compare a
    reconstruction against a reference CT volume. No such run exists yet, so
    `save` leaves those columns untouched rather than overwriting them.
    """

    def find(self, study_code: str) -> dict | None:
        """The study row, or None when there is no study with that code."""
        with connect() as connection:
            row = connection.execute(
                "select * from study where study_code = %s",
                (study_code,),
            ).fetchone()
        return None if row is None else _with_floats(row)

    def save(self, study_code: str, organ_id: int, date_time: datetime,
             status: str, *, patient_code: str = PLACEHOLDER_PATIENT_CODE,
             total_time_sec: float | None = None,
             volume_min: float | None = None,
             volume_max: float | None = None,
             volume_mean: float | None = None) -> None:
        """Create the study, or update it when it already exists.

        `status` is the stored value, not the wording of the business layer:
        callers translate it with `to_database_status` first.
        """
        with connect() as connection:
            connection.execute(_SAVE, {
                "study_code": study_code,
                "patient_code": patient_code,
                "organ_id": organ_id,
                "date_time": date_time,
                "status": status,
                "total_time_sec": total_time_sec,
                "volume_min": volume_min,
                "volume_max": volume_max,
                "volume_mean": volume_mean,
            })

    def delete(self, study_code: str) -> bool:
        """Remove the study and everything that hangs from it.

        The foreign keys cascade, so its projections, stages and lesions go with
        it. Returns whether a study was actually removed.
        """
        with connect() as connection:
            result = connection.execute(
                "delete from study where study_code = %s",
                (study_code,),
            )
            return result.rowcount > 0


def _self_check() -> int:
    """Write a throw-away study, read it back and compare. Cleans up after itself."""
    from .organ_repository import OrganRepository

    print("=" * 62)
    print("PERSISTENCE LAYER · STUDY REPOSITORY SELF-CHECK")
    print("=" * 62)

    organs = OrganRepository()
    studies = StudyRepository()
    code = "SELFCHECK-STUDY"
    failures: list[str] = []

    # The business layer spells the organ without accents.
    organ_id = organs.find_id_by_name("pulmon")
    print(f"  organ 'pulmon' resolves to organ_id {organ_id} "
          f"({organs.find_name_by_id(organ_id)})")

    # Values exactly as the business layer produces them.
    written = datetime.fromisoformat("2026-10-06T18:45:30")
    studies.delete(code)

    studies.save(code, organ_id, written,
                 to_database_status("Pendiente"))
    first = studies.find(code)
    print(f"  after create   : status={first['status']!r} "
          f"patient={first['patient_code']!r}")
    if first["status"] != "pendiente":
        failures.append("the status was not stored as 'pendiente'")
    if first["patient_code"] != PLACEHOLDER_PATIENT_CODE:
        failures.append("the study was not linked to the placeholder patient")
    if first["date_time"] != written:
        failures.append(f"the date came back as {first['date_time']}, not {written}")

    # Second save: the same study once processing has finished.
    studies.save(code, organ_id, written,
                 to_database_status("Reconstrucción completada"),
                 total_time_sec=0.023, volume_min=0.0,
                 volume_max=0.752, volume_mean=0.1234)
    second = studies.find(code)
    print(f"  after update   : status={second['status']!r} "
          f"time={second['total_time_sec']!r} mean={second['volume_mean']!r}")

    if to_business_status(second["status"]) != "Reconstrucción completada":
        failures.append("the status did not translate back to the business wording")
    if second["total_time_sec"] != 0.023:
        failures.append(f"0.023 s came back as {second['total_time_sec']}")
    if second["volume_mean"] != 0.1234:
        failures.append(f"0.1234 came back as {second['volume_mean']}")
    if not isinstance(second["total_time_sec"], float):
        failures.append("the numbers came back as decimals instead of floats")

    try:
        to_database_status("Casi listo")
        failures.append("an unknown status was accepted")
    except UnknownStatus:
        print("  unknown status : rejected, as it should be")

    removed = studies.delete(code)
    print(f"  cleanup        : study removed = {removed}")
    if studies.find(code) is not None:
        failures.append("the throw-away study was not removed")

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