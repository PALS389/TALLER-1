# Layer 2 Contracts and Independent Verification

Business code resides in `servicio/logica/` and uses English identifiers.
It receives storage, stage repositories and executors through dependency injection.
It does not define HTTP routes, SQL queries or storage locations.

## Preprocessing

`ProjectionPreprocessor.execute(projections)` accepts four decoded projections
and returns an independent, contiguous float32 array of shape `(4, 128, 128)`.
It rejects complex values, non-finite values and incorrect dimensions.
It preserves the projection scale used to train EN-1; it does not apply min-max
normalization or resize inputs. `read_projection` handles PNG scaling at decoding.
Use `create_pipeline(None, artifact_store)` to select this built-in preprocessor.

## Study Lifecycle

- `register_study` validates all four angles and rejects existing identifiers.
- `process_study` schedules work in the background by default.
- Concurrent processing of the same study raises `StudyInProgress`.
- Completed studies raise `StudyAlreadyCompleted` on another processing attempt.
- Failed studies may be retried; old errors and processing summaries are cleared.
- `get_results` reports current metadata without waiting for a background job.
- `get_result` waits for a local job and requires finished volume results.
- `close(wait=True)` stops new work and shuts down only an internally owned executor.

Duplicate protection uses a lock within one `StudyUseCases` instance.
Multiple processes or service instances require atomic uniqueness and work claims
from Layer 3. Jobs are not durable across service restarts.

## Metadata and Stage Persistence

Layer 3 must support these file-store methods:

```python
save_projections(study_id, projections)
read_projections(study_id)
save_volume(study_id, volume)
read_volume(study_id)
read_volume_bytes(study_id)
save_metadata(study_id, metadata)
read_metadata(study_id)
```

Reads raise `FileNotFoundError` for missing studies or artifacts. The legacy
adapter translates existing storage exceptions to this contract.
Metadata writes must preserve `status`, `error`, `metrics`, `statistics`,
`result_files`, `stage_statuses` and `progress`, along with registration fields.

An optional stage repository implements `record_waiting`, `record_start`,
`record_success` and `record_error`. The business layer also updates study
metadata after each stage event, even without a separate stage repository.
The orchestrator saves the reconstructed volume; use cases do not save it twice.

Illustrative `get_results` output during segmentation:

```json
{
  "study_id": "TEST-1",
  "status": "processing",
  "metrics": {},
  "statistics": {},
  "files": {},
  "error": null,
  "progress": {
    "stage": 3,
    "event": "start",
    "name": "segmentation",
    "completed_stages": 2
  },
  "stage_statuses": {
    "1": "success",
    "2": "success",
    "3": "start",
    "4": "waiting"
  }
}
```

The existing Layer 3 metadata facade still needs to retain these additional
fields. The existing HTTP reconstruction route still waits for the volume.
Neither integration change is required to test Layer 2 independently.

## Independent Tests

```powershell
.\.venv\Scripts\python.exe -m unittest pruebas.test_business_contracts pruebas.test_preprocessing pruebas.test_pipeline -v
python pruebas\prueba_capas.py
```

These tests use simulated storage, a real preprocessing stage and simulated
reconstruction, segmentation and mesh generation. They require no Supabase
credentials, trained weights, GPU or web server. They verify complete processing,
progress polling, duplicate rejection, failed storage writes and retries.
