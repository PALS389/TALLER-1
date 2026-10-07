# Integration Validation

## Verified Run

- Date: 2026-10-07.
- Dataset case: `lung_003`, four float32 NPY projections at 0, 45, 90 and 135 degrees.
- Supabase study: `EST-20261007-022851-7e75`.
- Submitted through the web interface; HTTP 202 returned before processing finished.
- Actual EN-1 reconstruction and EN-4 segmentation weights were used.
- Recovered volume: `(128, 128, 128)` with finite values.
- PostgreSQL contains four completed processing stages.
- Supabase Storage contains the volume, projections, metadata snapshot and meshes.
- Downloaded and parsed `organ.glb` (430836 bytes) and `tumor.glb` (7232 bytes); each contains one geometry.
- Metrics recovered from persistence match the HTTP response.
- Orthogonal slice viewer renders the result and responds to slider changes.
- Desktop and mobile screenshots are under ignored `datos/validation/`.
- End-to-end time until the viewer was available: 164.97 seconds. Reported pipeline time: 86.03 seconds.
- 39 automated tests pass; the closed-layer architecture check passes.

## Layer Contracts

The composition root now injects the trained four-stage pipeline and
`LegacyFileStoreAdapter` into `StudyUseCases`. Only Layer 3 knows storage paths,
Supabase credentials and SQL. Existing presentation/persistence Spanish contracts
remain compatible; new business identifiers are in English.

Layer 3 now implements `save_mesh(study_id, name, content) -> str`. Extended
metadata, including confidence metrics and artifact references, is stored as a
JSON snapshot in Supabase Storage. Existing relational study/stage records are
still updated; no database schema change was made. The relational study status
overrides the snapshot status when read. Database and object storage writes are
not a single atomic transaction.

The web client submits `wait_for_result=false` and polls
`GET /estudios/{study_id}`. Existing clients retain the wait-for-result default.
Open `/?study=EST-20261007-022851-7e75` to recover the completed result without
rerunning the models.
Projection input must be 128x128; do not silently resize the old 64x64 samples.

## Remaining Work

- Lung masks now use the morphological internal-air extraction from Bray's
  notebook. These shape checks are not clinical validation; evaluate organ
  segmentation on reconstructed volumes against appropriate reference masks.
- Tumor masks and probability maps are produced by segmentation but not yet
  persisted as separate artifacts. Individual lesion rows are not populated.
- Per-stage model IDs still need linking to EN-1/EN-4 records for model provenance.
- The in-process background executor is not a durable queue and does not survive
  server restarts; coordination across multiple workers is not implemented.
- Reduce persistence overhead before assuming a 30-90 second end-to-end target.
- EN-4 confidence is not calibrated clinical confidence. Regional labels represent
  array octants, not established anatomical localization.
- The offline Dice comparison for this one case was approximately 0.7209 on the
  original volume and 0.7101 on the EN-1 reconstruction. Validate across the dataset
  before drawing conclusions about medical performance.

## Repeat Checks

```powershell
.venv\Scripts\python.exe -m unittest discover -s pruebas -p "test_*.py"
.venv\Scripts\python.exe pruebas/prueba_capas.py
.venv\Scripts\python.exe -m pruebas.verify_stored_study EST-20261007-022851-7e75
```

The last command requires local credentials in ignored `.env`, network access
and the service running at `http://127.0.0.1:8001`. It only reads the stored study.
Weights, credentials, validation data and reports are not committed.

## Connected EN-42 Mesh Viewer

The presentation-layer viewer is at `/mesh-viewer.html?study=<study_id>` and is
also linked from completed study results. It adapts Bray's Three.js scene and
controls, with locally served pinned dependencies. The viewer retrieves metadata
without the volume payload and fetches GLB bytes through Layer 1 -> Layer 2 ->
Layer 3. Supabase credentials never reach the browser.

The `read_mesh(study_id, name) -> bytes` storage contract and
`get_mesh_glb(study_id, name) -> bytes` use case permit only the completed study's
registered `organ.glb` and `tumor.glb` artifacts. Arbitrary filenames and paths
are rejected. HTTP responses use `model/gltf-binary`.

Controls include organ/tumor visibility, organ opacity, orbit/zoom, a clipping
plane, automatic rotation, reset and a 30-second FPS measurement. An empty tumor
scene is supported without inventing lesion geometry. Invalid or unavailable
studies show a load error. The current test suite contains 57 passing tests.

The connected viewer was checked with the existing Supabase study: two GLB roots,
17904 organ triangles and 248 tumor triangles. Rendered-pixel samples were
nonzero on desktop and mobile, and changed during rotation. Visibility, opacity,
clipping, camera reset and a 30-second rotation test were exercised. The measured
mean was 143.2 FPS and the minimum was 28.8 FPS on this environment; the strict
30-FPS minimum is therefore not yet established. Screenshots are in ignored
`datos/validation/mesh-viewer-desktop.jpg` and `mesh-viewer-mobile.jpg`.

Read-only Supabase Storage downloads now retry transport failures up to three
attempts. Missing files and other application errors are not retried. Writes
are unchanged. The current development server for this viewer is on port 8002.

## Lung Surface Correction

The former `volume > 0.05` body-surface approximation was removed. The original
`EN42_mallas_y_visorv` file is a JSON notebook; its `mallas_en42.py` cell contains
the lung-mask code omitted from the first integration. `lung_mask.py` ports the
same air-erosion method and its multi-threshold/axis search fallback in English.
The extractor excludes exterior air and scores candidate components, extent,
bounding-box filling and solidity before generating a surface. It includes
predicted tumor voxels and checks the final mask. Failure raises
`InvalidLungMask`, so stage 4 fails rather than exporting a body-shaped block.

For the EN-1 reconstruction of `lung_003`, the resulting mask is identical to
Bray's original routine: 222608 voxels. The organ surface has 21564 triangles,
with mesh-to-mask volume error of 0.87 percent. Those values compare geometry
with the extracted heuristic mask, not segmentation with clinical ground truth.
The extractor also accepted the five original lung cases in Bray's delivery:
`lung_003`, `lung_010`, `lung_015`, `lung_059`, and `lung_026`.

Regression tests cover exterior/body exclusion, a trachea-to-air connection,
tumor inclusion, search fallback, invalid/constant volumes, float32 overflow,
local parity with Bray's routine and stage-4 failure propagation.
Historical completed studies retain their previous meshes until reprocessed
into a new study; they are not silently overwritten.

The corrected UI run is stored as `LUNG-FIX-MUXTX7ZQ` and can be opened at
`http://127.0.0.1:8002/mesh-viewer.html?study=LUNG-FIX-MUXTX7ZQ`.
The four-stage pipeline reported 85.88 seconds; the complete UI workflow took
161.78 seconds. Read-back verification confirmed the database stage records,
stored volume, 518804-byte organ GLB and 7232-byte tumor GLB.
Desktop (1280x900) and mobile (375x812) checks showed both loaded mesh roots,
nonzero rendered-pixel samples and a changing pixel signature during rotation.
Screenshots are in ignored `datos/validation/lung-fixed-desktop.jpg` and
`datos/validation/lung-fixed-mobile.jpg`.

The result remains irregular and must not be presented as two anatomically
validated complete lungs. The heuristic mask on the EN-1 reconstruction has
Dice overlap 0.9058 with the same heuristic applied to the original volume;
this is algorithm-to-algorithm agreement, not clinical accuracy. The original
case's extracted mask reaches the volume boundary and has unequal components.
Input coverage, reconstruction quality and lung-mask accuracy still need review.
