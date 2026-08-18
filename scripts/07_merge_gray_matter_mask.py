#!/usr/bin/env python3

"""Combine left and right blurred ribbon masks while preserving float values."""

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
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--binary-threshold",
        type=float,
        default=None,
        help="Optionally save a binary uint8 mask at this threshold",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for source in (args.left, args.right):
        if not source.is_file():
            raise FileNotFoundError(source)

    left_img = nib.load(args.left)
    right_img = nib.load(args.right)
    right_resampled = resample_to_img(
        right_img, left_img, interpolation="continuous", force_resample=True
    )
    left = left_img.get_fdata(dtype=np.float32)
    right = right_resampled.get_fdata(dtype=np.float32)
    combined = np.maximum(left, right)

    if args.binary_threshold is None:
        data = combined.astype(np.float32)
        dtype = np.float32
    else:
        data = (combined >= args.binary_threshold).astype(np.uint8)
        dtype = np.uint8

    header = left_img.header.copy()
    header.set_data_dtype(dtype)
    output = nib.Nifti1Image(data, left_img.affine, header)
    output.set_qform(left_img.get_qform(), int(left_img.header["qform_code"]))
    output.set_sform(left_img.get_sform(), int(left_img.header["sform_code"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    nib.save(output, args.output)
    print(f"Saved gray-matter mask: {args.output}")


if __name__ == "__main__":
    main()

