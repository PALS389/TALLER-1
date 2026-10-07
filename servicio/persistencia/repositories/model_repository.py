"""
Capa 3 · Persistencia · Model repository.

Reads and writes the `model` table, which answers one question: which model or
method produced a given result.

A trained network and a closed-form method are both recorded here. The
reconstruction the service performs today has no trainable parameters, so its
row carries no weights file and no training date; those two attributes are
optional for exactly that reason. The reconstruction model also serves both
organs, so its `organ_id` is left empty.

Run a self-check with:

    python -m servicio.persistencia.repositories.model_repository
"""
from __future__ import annotations

from datetime import date

from ..connection import connect

RECONSTRUCTION = "reconstruccion"
SEGMENTATION = "segmentacion"

_INSERT = """
    insert into model (organ_id, model_name, model_type, version,
                       weights_path, trained_on)
    values (%(organ_id)s, %(model_name)s, %(model_type)s, %(version)s,
            %(weights_path)s, %(trained_on)s)
    on conflict (model_name, version) do nothing
    returning model_id
"""


class ModelRepository:
    """Access to the `model` table."""

    def find(self, model_name: str, version: str) -> dict | None:
        """The model row, or None when that name and version are not stored."""
        with connect() as connection:
            return connection.execute(
                "select * from model where model_name = %s and version = %s",
                (model_name, version),
            ).fetchone()

    def find_by_id(self, model_id: int) -> dict | None:
        """The model row by identifier, or None."""
        with connect() as connection:
            return connection.execute(
                "select * from model where model_id = %s", (model_id,)
            ).fetchone()

    def find_or_create(self, model_name: str, model_type: str, version: str,
                       *, organ_id: int | None = None,
                       weights_path: str | None = None,
                       trained_on: date | None = None) -> int:
        """Identifier of the model, registering it the first time it is seen.

        Two runs of the same method must not create two rows, so the name and
        version together identify a model. An existing row is returned
        untouched: whoever registered it knew more about it than a later caller
        that only has its name.
        """
        parameters = {"organ_id": organ_id, "model_name": model_name,
                      "model_type": model_type, "version": version,
                      "weights_path": weights_path, "trained_on": trained_on}
        with connect() as connection:
            with connection.cursor() as cursor:
                row = cursor.execute(_INSERT, parameters).fetchone()
                if row is None:
                    # The row already existed, so the insert returned nothing.
                    row = cursor.execute(
                        "select model_id from model "
                        "where model_name = %s and version = %s",
                        (model_name, version),
                    ).fetchone()
                return row["model_id"]

    def delete(self, model_id: int) -> bool:
        """Remove a model. Fails while a processing stage still refers to it."""
        with connect() as connection:
            result = connection.execute(
                "delete from model where model_id = %s", (model_id,))
            return result.rowcount > 0


def _self_check() -> int:
    """Register a throw-away model twice and check it is stored once."""
    print("=" * 62)
    print("PERSISTENCE LAYER · MODEL REPOSITORY SELF-CHECK")
    print("=" * 62)

    models = ModelRepository()
    name, version = "SELFCHECK-method", "v1"
    failures: list[str] = []

    existing = models.find(name, version)
    if existing is not None:
        models.delete(existing["model_id"])

    # A method without trainable parameters: no weights, no training date.
    first = models.find_or_create(name, RECONSTRUCTION, version)
    print(f"  registered           : model_id {first}")

    row = models.find_by_id(first)
    print(f"  weights_path         : {row['weights_path']}")
    print(f"  trained_on           : {row['trained_on']}")
    print(f"  organ_id             : {row['organ_id']}")
    if row["weights_path"] is not None or row["trained_on"] is not None:
        failures.append("a method without training was stored with weights")
    if row["organ_id"] is not None:
        failures.append("a universal model was tied to one organ")

    # Calling it again must not create a second row.
    second = models.find_or_create(name, RECONSTRUCTION, version)
    print(f"  registered again     : model_id {second}")
    if second != first:
        failures.append(f"a second row was created ({first} and {second})")

    if models.delete(first):
        print("  cleanup              : model removed")
    else:
        failures.append("the throw-away model was not removed")

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