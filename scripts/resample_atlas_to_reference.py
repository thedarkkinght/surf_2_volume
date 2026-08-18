#!/usr/bin/env python3

"""Resample an integer atlas to a reference image without overwriting the source."""

from __future__ import annotations

import argparse
from pathlib import Path

import nibabel as nib
import numpy as np
from nilearn.image import resample_to_img


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.atlas.is_file():
        raise FileNotFoundError(args.atlas)
    if not args.reference.is_file():
        raise FileNotFoundError(args.reference)
    if args.output.resolve() == args.atlas.resolve():
        raise ValueError("Output must not overwrite the input atlas")

    atlas = nib.load(args.atlas)
    reference = nib.load(args.reference)
    resampled = resample_to_img(
        atlas, reference, interpolation="nearest", force_resample=True
    )
    labels = np.rint(resampled.get_fdata()).astype(np.int16)
    header = reference.header.copy()
    header.set_data_dtype(np.int16)
    output = nib.Nifti1Image(labels, reference.affine, header)
    output.set_qform(reference.get_qform(), int(reference.header["qform_code"]))
    output.set_sform(reference.get_sform(), int(reference.header["sform_code"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    nib.save(output, args.output)
    print(f"Saved resampled atlas: {args.output}")


if __name__ == "__main__":
    main()

