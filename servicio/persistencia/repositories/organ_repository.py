"""
Capa 3 · Persistencia · Organ repository.

Reads the closed set of organs the system works on.

The business layer names an organ as `pulmon` or `higado`, in lower case and
without accents, while the database stores the display names `Pulmon` and
`Higado` with their accents. Matching is done on a normalised form, so neither
side needs to know how the other spells it, and adding a third organ later
needs no change to this code.
"""
from __future__ import annotations

import unicodedata

from ..connection import connect


class OrganNotFound(LookupError):
    """No organ in the database matches the given name or identifier."""


def normalise(name: str) -> str:
    """Lower case, no accents, no surrounding blanks.

    'Pulmon', 'pulmon' and ' PULMON ' all normalise to the same text.
    """
    decomposed = unicodedata.normalize("NFD", name.strip().lower())
    return "".join(char for char in decomposed
                   if unicodedata.category(char) != "Mn")


class OrganRepository:
    """Read-only access to the `organ` table.

    The rows are seed data created by the schema, so this repository offers no
    way to insert or delete them.
    """

    def all(self) -> list[dict]:
        """Every organ, ordered by identifier."""
        with connect() as connection:
            return connection.execute(
                "select organ_id, organ_name, anatomical_region "
                "from organ order by organ_id"
            ).fetchall()

    def find_id_by_name(self, name: str) -> int:
        """Identifier of the organ whose name matches, ignoring case and accents."""
        wanted = normalise(name)
        organs = self.all()
        for organ in organs:
            if normalise(organ["organ_name"]) == wanted:
                return organ["organ_id"]
        known = ", ".join(organ["organ_name"] for organ in organs)
        raise OrganNotFound(f"Unknown organ {name!r}. Known organs: {known}.")

    def find_name_by_id(self, organ_id: int) -> str:
        """Display name stored in the database, accents included."""
        with connect() as connection:
            row = connection.execute(
                "select organ_name from organ where organ_id = %s",
                (organ_id,),
            ).fetchone()
        if row is None:
            raise OrganNotFound(f"No organ has identifier {organ_id}.")
        return row["organ_name"]