"""
Capa 3 · Persistencia · Processing stage repository.

Reads and writes the `processing_stage` table, which records the four stages of
the pipeline: what ran, when, with which model, and how it ended.

A stage that cannot run because its model does not exist yet is recorded as
omitted rather than left out. That is what lets the interface show the whole
pipeline and say which parts were skipped, instead of silently showing fewer
stages than the study has.

The stage name is derived from its number, so a caller cannot store stage 2
under the name of stage 3.

Run a self-check with:

    python -m servicio.persistencia.repositories.processing_stage_repository
"""
from __future__ import annotations

from datetime import datetime

from ..connection import connect

# The four stages of the pipeline, in order. The names match the values the
# database accepts for stage_name.
STAGE_NAMES = {
    1: "Preprocesamiento",
    2: "Reconstrucción",
    3: "Segmentación",
    4: "Mallas",
}

WAITING = "en espera"
RUNNING = "ejecutando"
COMPLETED = "completada"
SKIPPED = "omitida"
FAILED = "error"

_SAVE = """
    insert into processing_stage (study_code, model_id, stage_number, stage_name,
                                 started_at, finished_at, stage_status)
    values (%(study_code)s, %(model_id)s, %(stage_number)s, %(stage_name)s,
            %(started_at)s, %(finished_at)s, %(stage_status)s)
    on conflict (study_code, stage_number) do update set
        model_id     = excluded.model_id,
        stage_name   = excluded.stage_name,
        started_at   = excluded.started_at,
        finished_at  = excluded.finished_at,
        stage_status = excluded.stage_status
"""


class UnknownStage(ValueError):
    """A stage number outside the four the pipeline defines."""


def stage_name(stage_number: int) -> str:
    """Name of the stage that bears that number."""
    try:
        return STAGE_NAMES[stage_number]
    except KeyError:
        raise UnknownStage(
            f"There is no stage {stage_number}. The pipeline has stages "
            f"{', '.join(str(number) for number in STAGE_NAMES)}."
        ) from None


class ProcessingStageRepository:
    """Access to the `processing_stage` table."""

    def save(self, study_code: str, stage_number: int, started_at: datetime,
             stage_status: str, *, model_id: int | None = None,
             finished_at: datetime | None = None) -> None:
        """Record a stage of a study, replacing it when already recorded.

        `model_id` is left empty for stages that use no model.
        """
        with connect() as connection:
            connection.execute(_SAVE, {
                "study_code": study_code,
                "model_id": model_id,
                "stage_number": stage_number,
                "stage_name": stage_name(stage_number),
                "started_at": started_at,
                "finished_at": finished_at,
                "stage_status": stage_status,
            })

    def find_by_study(self, study_code: str) -> list[dict]:
        """Stages of a study, in pipeline order. Empty when none are recorded."""
        with connect() as connection:
            return connection.execute(
                "select stage_id, study_code, model_id, stage_number, stage_name, "
                "started_at, finished_at, stage_status "
                "from processing_stage where study_code = %s "
                "order by stage_number",
                (study_code,),
            ).fetchall()


def _self_check() -> int:
    """Record stages against a throw-away study. Cleans up after itself."""
    from datetime import timedelta

    from .model_repository import ModelRepository, RECONSTRUCTION
    from .organ_repository import OrganRepository
    from .study_repository import StudyRepository, to_database_status

    print("=" * 62)
    print("PERSISTENCE LAYER · PROCESSING STAGE SELF-CHECK")
    print("=" * 62)

    organs = OrganRepository()
    studies = StudyRepository()
    models = ModelRepository()
    stages = ProcessingStageRepository()
    code = "SELFCHECK-STAGE"
    failures: list[str] = []

    studies.delete(code)
    registered = datetime.fromisoformat("2026-10-06T18:45:30")
    studies.save(code, organs.find_id_by_name("pulmon"), registered,
                 to_database_status("Reconstrucción completada"),
                 total_time_sec=0.023)

    model_id = models.find_or_create("SELFCHECK-method", RECONSTRUCTION, "v1")

    # Stage 1 uses no model. Stage 2 does, and its end is derived from the
    # duration the business layer measured.
    stages.save(code, 1, registered, COMPLETED)
    stages.save(code, 2, registered, COMPLETED, model_id=model_id,
                finished_at=registered + timedelta(seconds=0.023))
    # Stages 3 and 4 cannot run until their models exist.
    stages.save(code, 3, registered, SKIPPED)
    stages.save(code, 4, registered, SKIPPED)

    recorded = stages.find_by_study(code)
    print(f"  recorded             : {len(recorded)} stages")
    for stage in recorded:
        model = stage["model_id"] if stage["model_id"] is not None else "-"
        print(f"    {stage['stage_number']}  {stage['stage_name']:<18}"
              f"{stage['stage_status']:<12} model={model}")

    if [stage["stage_number"] for stage in recorded] != [1, 2, 3, 4]:
        failures.append("the stages did not come back in pipeline order")
    if recorded[0]["model_id"] is not None:
        failures.append("stage 1 was stored with a model it does not use")
    if recorded[1]["model_id"] != model_id:
        failures.append("stage 2 was not linked to its model")
    if recorded[1]["finished_at"] is None:
        failures.append("the end of stage 2 was not recorded")
    if recorded[2]["stage_status"] != SKIPPED:
        failures.append("stage 3 was not recorded as omitted")

    # Re-processing replaces a stage instead of duplicating it.
    stages.save(code, 2, registered, FAILED, model_id=model_id)
    again = stages.find_by_study(code)
    if len(again) != 4:
        failures.append(f"re-saving stage 2 left {len(again)} rows instead of 4")
    elif again[1]["stage_status"] != FAILED:
        failures.append("re-saving stage 2 did not update its status")
    else:
        print("  re-saving stage 2    : replaced, still 4 rows")

    try:
        stage_name(5)
        failures.append("stage 5 was accepted")
    except UnknownStage:
        print("  stage 5              : rejected, as it should be")

    studies.delete(code)
    if stages.find_by_study(code):
        failures.append("the stages outlived the study they belong to")
    else:
        print("  cleanup              : study and stages removed")
    models.delete(model_id)

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