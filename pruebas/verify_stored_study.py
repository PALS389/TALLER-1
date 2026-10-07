"""Read-only verification of a completed integration study in Supabase."""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import numpy as np
import requests
import trimesh

from servicio.persistencia.almacen_archivos import AlmacenArchivos
from servicio.persistencia.repositories.processing_stage_repository import ProcessingStageRepository, COMPLETED
from servicio.persistencia import layout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("study_id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    response = requests.get(f"{args.base_url}/estudios/{args.study_id}", timeout=60)
    response.raise_for_status()
    result = response.json()
    if result["estado"] != "Reconstrucción completada":
        raise RuntimeError("Study is not complete yet.")
    store = AlmacenArchivos()
    metadata = store.leer_metadatos(args.study_id)
    volume = store.leer_volumen(args.study_id)
    assert volume.shape == (128, 128, 128) and np.isfinite(volume).all()
    assert metadata["metricas"] == result["metricas"]
    stages = ProcessingStageRepository().find_by_study(args.study_id)
    assert len(stages) == 4 and all(stage["stage_status"] == COMPLETED for stage in stages)
    meshes = {}
    for name in ("organ.glb", "tumor.glb"):
        content = store._almacen.read_bytes(layout.artifact_path(args.study_id, name))
        assert content[:4] == b"glTF"
        scene = trimesh.load(io.BytesIO(content), file_type="glb", force="scene")
        meshes[name] = {"bytes": len(content), "geometries": len(scene.geometry)}
    report = {"study_id": args.study_id, "status": "completed",
              "volume_shape": list(volume.shape), "stages": [s["stage_status"] for s in stages],
              "meshes": meshes, "metrics": metadata["metricas"]}
    output = Path("datos/validation") / f"{args.study_id}-verification.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"study_id": args.study_id, "verified": True, "meshes": meshes}))


if __name__ == "__main__":
    main()
