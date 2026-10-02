"""Utilities for combining label volumes."""

from os import PathLike
from pathlib import Path

import nibabel as nib
import numpy as np
from nibabel.processing import resample_from_to


def merge_label_volumes(
    left: str | PathLike,
    right: str | PathLike,
    subcortical: str | PathLike,
    output: str | PathLike,
) -> Path:
    """Merge labels with priority left > right > subcortical.

    Inputs on different grids are nearest-neighbor resampled to the left image
    grid. Zero is treated as background.
    """
    left_img = nib.load(str(left))
    target = (left_img.shape[:3], left_img.affine)

    def on_target(path):
        image = nib.load(str(path))
        if image.shape[:3] != target[0] or not np.allclose(image.affine, target[1]):
            image = resample_from_to(image, target, order=0)
        data = np.asarray(image.dataobj)
        if data.ndim != 3:
            raise ValueError(f"Expected a 3D label volume: {path}")
        return np.rint(data).astype(np.int32)

    left_data = on_target(left)
    right_data = on_target(right)
    sub_data = on_target(subcortical)
    merged = left_data.copy()
    take = (merged == 0) & (right_data != 0)
    merged[take] = right_data[take]
    take = (merged == 0) & (sub_data != 0)
    merged[take] = sub_data[take]

    header = left_img.header.copy()
    header.set_data_dtype(np.int16)
    nib.save(nib.Nifti1Image(merged.astype(np.int16), left_img.affine, header), str(output))
    return Path(output)
