#!/usr/bin/env python3

"""Resample left and right fsLR label files to fsaverage with nearest labels."""

from __future__ import annotations

import argparse
from pathlib import Path

import nibabel as nib
from neuromaps.transforms import fslr_to_fsaverage, fslr_to_fslr


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", required=True, type=Path, help="Left fsLR GIFTI label file")
    parser.add_argument("--right", required=True, type=Path, help="Right fsLR GIFTI label file")
    parser.add_argument("--left-output", required=True, type=Path)
    parser.add_argument("--right-output", required=True, type=Path)
    parser.add_argument("--density", default="164k", help="Target fsLR/fsaverage density")
    return parser.parse_args()


def resample_label(source: Path, hemisphere: str, density: str):
    fs_l_r = fslr_to_fslr(
        str(source), target_density=density, hemi=hemisphere, method="nearest"
    )
    return fslr_to_fsaverage(
        fs_l_r[0], target_density=density, hemi=hemisphere, method="nearest"
    )[0]


def main() -> None:
    args = parse_args()
    for input_path in (args.left, args.right):
        if not input_path.is_file():
            raise FileNotFoundError(input_path)

    args.left_output.parent.mkdir(parents=True, exist_ok=True)
    args.right_output.parent.mkdir(parents=True, exist_ok=True)

    left = resample_label(args.left, "L", args.density)
    right = resample_label(args.right, "R", args.density)
    nib.save(left, args.left_output)
    nib.save(right, args.right_output)

    print(f"Saved {args.left_output}")
    print(f"Saved {args.right_output}")


if __name__ == "__main__":
    main()

