#!/usr/bin/env python3

"""Merge left cortex, right cortex, and subcortex into one integer NIfTI atlas."""

from __future__ import annotations

import argparse
from pathlib import Path

import nibabel as nib
import numpy as np
from nilearn.image import resample_to_img


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", required=True, type=Path)
    parser.add_argument("--right", required=True, type=Path)
    parser.add_argument("--subcortical", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--priority",
        choices=("left-right-subcortical", "subcortical-left-right"),
        default="left-right-subcortical",
        help="Label precedence in overlapping voxels",
    )
    return parser.parse_args()


def load_and_resample(source: Path, reference: nib.spatialimages.SpatialImage) -> np.ndarray:
    image = nib.load(source)
    resampled = resample_to_img(
        image, reference, interpolation="nearest", force_resample=True
    )
    data = resampled.get_fdata()
    if not np.isfinite(data).all():
        raise ValueError(f"Non-finite values found in {source}")
    return data


def assign_if_empty(combined: np.ndarray, source: np.ndarray) -> None:
    mask = (combined == 0) & (source > 0)
    combined[mask] = source[mask]


def main() -> None:
    args = parse_args()
    sources = (args.left, args.right, args.subcortical)
    for source in sources:
        if not source.is_file():
            raise FileNotFoundError(source)
    if args.output.resolve() in {source.resolve() for source in sources}:
        raise ValueError("Output must not overwrite an input atlas")

    reference = nib.load(args.subcortical)
    left = load_and_resample(args.left, reference)
    right = load_and_resample(args.right, reference)
    subcortical = reference.get_fdata()

    combined = np.zeros(reference.shape, dtype=np.float64)
    if args.priority == "left-right-subcortical":
        ordered = (left, right, subcortical)
    else:
        ordered = (subcortical, left, right)
    for source in ordered:
        assign_if_empty(combined, source)

    rounded = np.rint(combined)
    limits = np.iinfo(np.int16)
    if rounded.min() < limits.min or rounded.max() > limits.max:
        raise ValueError("Atlas labels exceed the int16 range")
    labels = rounded.astype(np.int16)

    header = reference.header.copy()
    header.set_data_dtype(np.int16)
    output = nib.Nifti1Image(labels, reference.affine, header)
    output.set_qform(reference.get_qform(), int(reference.header["qform_code"]))
    output.set_sform(reference.get_sform(), int(reference.header["sform_code"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    nib.save(output, args.output)
    print(f"Saved merged atlas: {args.output}")


if __name__ == "__main__":
    main()

