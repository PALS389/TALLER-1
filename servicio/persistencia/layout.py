"""
Capa 3 · Persistencia · Storage layout.

Single definition of where each file of a study lives. Both the file store and
the metadata store derive paths from here, so a projection is written to the
same place whose path is later recorded in the database.

The identifier is checked before it becomes part of a path. The local store
this layer replaces refused identifiers such as `../other`, and the same
guarantee has to hold: an identifier must never be able to name a file outside
its own study folder.
"""
from __future__ import annotations

import re

# Same shape the business layer accepts for an identifier.
STUDY_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class InvalidStudyId(ValueError):
    """The identifier cannot be used to build a path."""


def check_study_id(study_id: str) -> str:
    """The identifier, confirmed safe to use in a path."""
    if not isinstance(study_id, str) or not STUDY_ID.match(study_id):
        raise InvalidStudyId(
            f"Invalid study identifier: {study_id!r}. Only letters, digits, "
            f"'-' and '_' are allowed, up to 64 characters."
        )
    return study_id


def study_folder(study_id: str) -> str:
    """Folder that holds every file of a study."""
    return check_study_id(study_id)


def projection_path(study_id: str, angle_degrees: int) -> str:
    """File of the radiograph taken at that angle."""
    return f"{study_folder(study_id)}/projections/angle_{int(angle_degrees):03d}.npy"


def volume_path(study_id: str) -> str:
    """File of the reconstructed volume."""
    return f"{study_folder(study_id)}/volume.npy"


def artifact_path(study_id: str, name: str) -> str:
    if name not in {"metadata.json", "organ.glb", "tumor.glb"}:
        raise ValueError("Unsupported study artifact.")
    return f"{study_folder(study_id)}/{name}"
