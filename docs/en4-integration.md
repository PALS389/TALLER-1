# EN-4 Segmentation Integration

`EN4LungSegmenter` implements the `TumorSegmenter` protocol using the architecture
and inference conventions from the supplied `EN_04.ipynb` notebook.
All business identifiers, output fields and error messages are in English.

## Model Contract

- Input: a finite float32 volume with shape `(128, 128, 128)`.
- Model input: `(1, 1, 128, 128, 128)`; values are preserved without per-volume rescaling.
- Output: a sigmoid probability map, a uint8 tumor mask, and eight regional summaries.
- Mask rule: probability strictly greater than `0.5`, matching the notebook.
- Global confidence: mean probability of predicted tumor voxels; zero for an empty mask.
- Regions: upper/lower, front/back, left/right array octants, split at index 64.
- Regional volume: predicted voxel count times the product of voxel spacing.

The default spacing is `(2.5, 2.5, 2.5)` mm, as in EN-4. Patient orientation and
physical spacing must be verified from the source data before interpreting
these array octants as anatomical regions or the volumes as patient measurements.
Sigmoid probabilities are model scores, not calibrated clinical certainty.

## Local Setup

The supplied weights were copied to `modelos/en4_segmentador_pulmon.pth`.
Weights remain ignored by Git. Install processing dependencies with:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-processing.txt
```

```python
from servicio.logica.tuberia.en4_segmentation import EN4LungSegmenter

segmenter = EN4LungSegmenter(device="cpu")
result = segmenter.segment(volume)
mask = result.tumor_mask
probabilities = result.probability_map
regions = result.regional_confidence
```

`create_pipeline(preprocessor, artifact_store)` composes EN-1, EN-4 and EN-4.2.
The caller supplies an artifact store implementing `save_volume` and `save_mesh`.
Pass `None` as the preprocessor to use the built-in scale-preserving
`ProjectionPreprocessor`, or inject a compatible preprocessor.
Inject the pipeline into `StudyUseCases`.
The existing service composition still uses the reconstruction-only path;
the Layer 3 facade does not yet implement the full artifact contract.

The orchestrator includes `regional_confidence` and `confidence_threshold` in
its result metrics. Layer 3 must preserve those metrics when saving results.
Saving masks and probability maps as binary artifacts requires a corresponding
Layer 3 contract; this integration returns them in memory.

## Evaluation Limits

The supplied JSON contains historical test-case results; it is not a lookup
table for new studies. Regional scores are recalculated for every input.
The notebook trains and evaluates EN-4 on original volumes, not EN-1 predictions.
Validate reconstruction-to-segmentation performance with paired data before
claiming the same evaluation performance for the combined pipeline.
Dice evaluation requires a reference tumor mask and is not calculated for
new studies without ground truth.

An empty tumor mask produces an empty `tumor.glb` scene, rather than a fabricated
tumor surface. A non-empty mask with fewer than eight voxels is still rejected
by the current mesh generator as too small for its surface extraction settings.

## Verification

Thirty tests pass across preprocessing, the pipeline, business contracts, EN-4 and GLB exports.
The supplied EN-1 and EN-4 checkpoints both load on CPU. Full EN-4 inference was
checked at `(128, 128, 128)`. The composed trained pipeline was also checked with
synthetic projections, an identity preprocessor and an in-memory artifact store;
it returned eight region summaries and two readable GLB files. This checks
integration contracts, not segmentation accuracy on reconstructed patient data.

```powershell
.\.venv\Scripts\python.exe -m unittest pruebas.test_preprocessing pruebas.test_pipeline pruebas.test_business_contracts pruebas.test_segmentation pruebas.test_meshes -v
python pruebas\prueba_capas.py
```
