"""Wrappers for FreeSurfer commands."""

from copy import deepcopy
import subprocess
from os import PathLike
from pathlib import Path

import nibabel as nib
import numpy as np
from nibabel.freesurfer import read_geometry
from nibabel.gifti import GiftiImage
from scipy.spatial import cKDTree


def resample_surface_label(
    source_label: str | PathLike,
    srcsubject: str,
    trgsubject: str,
    hemi: str,
    subjects_dir: str | PathLike,
    output: str | PathLike,
) -> Path:
    """Nearest-neighbor resample a GIFTI label using FreeSurfer sphere.reg files.

    This implements ``mri_surf2surf --mapmethod nnf`` without running FreeSurfer.
    The registration surfaces must already exist under ``subjects_dir``.
    """
    if hemi not in {"lh", "rh"}:
        raise ValueError("hemi must be 'lh' or 'rh'")
    subjects_dir = Path(subjects_dir)
    src_sphere = subjects_dir / srcsubject / "surf" / f"{hemi}.sphere.reg"
    trg_sphere = subjects_dir / trgsubject / "surf" / f"{hemi}.sphere.reg"
    source_coords, _ = read_geometry(str(src_sphere))
    target_coords, _ = read_geometry(str(trg_sphere))
    nearest = cKDTree(source_coords).query(target_coords, k=1)[1]

    image = nib.load(str(source_label))
    if not isinstance(image, GiftiImage):
        raise ValueError("source_label must be a GIFTI file")
    if any(array.data.ndim != 1 or len(array.data) != len(source_coords) for array in image.darrays):
        raise ValueError("GIFTI label vertex count does not match the source sphere")
    result = deepcopy(image)
    for array in result.darrays:
        array.data = np.asarray(array.data)[nearest].astype(np.int32)
        array.dims = list(array.data.shape)
        array.intent = int(nib.nifti1.intent_codes["NIFTI_INTENT_LABEL"])
        array.datatype = int(nib.nifti1.data_type_codes["NIFTI_TYPE_INT32"])
    nib.save(result, str(output))
    return Path(output)

def mri_surf2surf(
    srcsubject: str,
    trgsubject: str,
    source_value: str | PathLike,
    target_value: str | PathLike,
    hemi: str,
    *,
    mapmethod: str = "nnf",
    executable: str | PathLike = "mri_surf2surf",
) -> Path:
    """Run FreeSurfer's mri_surf2surf for one hemisphere and value file."""
    if hemi not in {"lh", "rh"}:
        raise ValueError("hemi must be 'lh' or 'rh'")
    if mapmethod not in {"nnf", "nnfr"}:
        raise ValueError("mapmethod must be 'nnf' or 'nnfr'")
    subprocess.run(
        [
            str(executable),
            "--srcsubject", srcsubject,
            "--trgsubject", trgsubject,
            "--srcsurfval", str(source_value),
            "--trgsurfval", str(target_value),
            "--mapmethod", mapmethod,
            "--hemi", hemi,
        ],
        check=True,
    )
    return Path(target_value)
