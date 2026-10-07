"""Prepare lossless projection inputs from a processed dataset archive."""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import re
from zipfile import ZipFile

import numpy as np


def prepare_case(archive_path: Path, output_directory: Path, case_id: str) -> None:
    if not re.fullmatch(r"lung_\d+", case_id):
        raise ValueError("Expected a lung case identifier such as lung_003.")
    with ZipFile(archive_path) as archive:
        arrays = {
            suffix: np.load(io.BytesIO(archive.read(f"processed/pulmon/{case_id}_{suffix}.npy")),
                            allow_pickle=False)
            for suffix in ("proj", "vol", "tumor")
        }
    for suffix, array in arrays.items():
        expected = (4, 128, 128) if suffix == "proj" else (128, 128, 128)
        if array.shape != expected or not np.isfinite(array).all():
            raise ValueError(f"Invalid {suffix} array: expected finite values of shape {expected}.")
    if not np.isin(arrays["tumor"], (0, 1)).all():
        raise ValueError("The reference tumor mask must be binary.")
    output_directory.mkdir(parents=True, exist_ok=True)
    # Use NPY rather than scaled PNG: some projections exceed uint16/1000.
    for index, angle in enumerate((0, 45, 90, 135)):
        path = output_directory / f"{case_id}_{angle:03d}.npy"
        np.save(path, arrays["proj"][index].astype(np.float32), allow_pickle=False)
        print(f"Prepared {path.name}: (128, 128), float32")
    np.save(output_directory / f"{case_id}_vol.npy", arrays["vol"].astype(np.float32), allow_pickle=False)
    np.save(output_directory / f"{case_id}_tumor.npy", arrays["tumor"].astype(np.uint8), allow_pickle=False)
    print(f"Validation case saved to {output_directory.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--case", default="lung_003")
    parser.add_argument("--output", type=Path, default=Path("datos/validation/lung_003"))
    arguments = parser.parse_args()
    prepare_case(arguments.archive, arguments.output, arguments.case)
