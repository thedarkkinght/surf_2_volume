"""End-to-end CIFTI label conversion pipeline."""

from collections.abc import Mapping, Sequence
import json
import math
from os import PathLike
from pathlib import Path

import nibabel as nib
import numpy as np

from .afni import resample_gifti_with_m2m, spackle_surface_to_volume
from .freesurfer import resample_surface_label
from .volume import merge_label_volumes
from .workbench import separate_cifti
from .references import ensure_reference_files


_AUTO_THRESHOLDS = (
    0.01, 0.025, 0.05, 0.075, 0.10, 0.15,
    0.20, 0.25, 0.30, 0.40, 0.50, 0.75,
)


def _cifti_cortical_distribution(cifti_file: Path) -> dict[int, float]:
    """Return each cortical label's share of source CIFTI cortical vertices."""
    from nibabel.cifti2 import cifti2_axes

    image = nib.load(str(cifti_file))
    if len(image.shape) != 2:
        raise ValueError("reference_cifti must be a two-dimensional dlabel file")
    label_axis = image.header.get_axis(0)
    brain_axis = image.header.get_axis(1)
    if not isinstance(label_axis, cifti2_axes.LabelAxis) or not isinstance(
        brain_axis, cifti2_axes.BrainModelAxis
    ):
        raise ValueError("reference_cifti must contain a LabelAxis and BrainModelAxis")
    if image.shape[0] != 1:
        raise ValueError("Automatic threshold selection currently supports one CIFTI label map")

    cortical = np.isin(
        brain_axis.name,
        ("CIFTI_STRUCTURE_CORTEX_LEFT", "CIFTI_STRUCTURE_CORTEX_RIGHT"),
    )
    values = np.rint(np.asarray(image.dataobj)[0, cortical]).astype(np.int32)
    label_names = label_axis.label[0]
    valid_keys = {
        int(key) for key, (name, _) in label_names.items()
        if int(key) != 0 and name != "???"
    }
    counts = {key: int(np.count_nonzero(values == key)) for key in valid_keys}
    counts = {key: count for key, count in counts.items() if count > 0}
    total = sum(counts.values())
    if not total:
        raise ValueError("reference_cifti contains no assigned cortical parcel vertices")
    return {key: count / total for key, count in counts.items()}


def _distribution_error(prediction: Path, reference: dict[int, float]) -> float:
    """Mean absolute difference between normalized CIFTI and voxel parcel shares."""
    image = nib.load(str(prediction))
    if len(image.shape) != 3:
        raise ValueError("Predicted atlas must be a 3D label volume")
    data = np.rint(np.asarray(image.dataobj)).astype(np.int32)
    counts = {key: int(np.count_nonzero(data == key)) for key in reference}
    total = sum(counts.values())
    if not total:
        return float("inf")
    return float(np.mean([
        abs(counts[key] / total - share) for key, share in reference.items()
    ]))


def select_best_threshold(
    outputs: Mapping[float, str | PathLike],
    reference_cifti: str | PathLike,
    *,
    top_n: int = 3,
    report_file: str | PathLike | None = None,
) -> list[tuple[float, Path, float]]:
    """Rank outputs by source CIFTI cortical parcel-share similarity."""
    if not outputs:
        raise ValueError("outputs must contain at least one threshold and volume")
    if not isinstance(top_n, int) or top_n < 1:
        raise ValueError("top_n must be a positive integer")
    reference_path = Path(reference_cifti)
    if not reference_path.is_file():
        raise FileNotFoundError(f"reference_cifti not found: {reference_path}")
    reference = _cifti_cortical_distribution(reference_path)
    paths = {float(threshold): Path(path) for threshold, path in outputs.items()}
    scores = {
        threshold: _distribution_error(path, reference)
        for threshold, path in paths.items()
    }
    finite_scores = {threshold: score for threshold, score in scores.items() if math.isfinite(score)}
    if not finite_scores:
        raise ValueError(
            "No cortical labels from the input CIFTI were found in any output; "
            "check that the source and output label IDs match."
        )
    ranked = sorted(finite_scores, key=finite_scores.get)[:top_n]
    report = {
        "criterion": "mean_absolute_difference_in_normalized_cortical_parcel_shares",
        "definition": "mean(abs(predicted cortical voxel share - source CIFTI cortical vertex share))",
        "reference_cifti": str(reference_path.resolve()),
        "selected_thresholds": [
            {"rank": rank, "threshold": value, "score": scores[value]}
            for rank, value in enumerate(ranked, start=1)
        ],
        "scores": {str(value): score for value, score in scores.items()},
    }
    if report_file is not None:
        report_path = Path(report_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Top {len(ranked)} ribbon thresholds by distribution similarity:")
    for rank, value in enumerate(ranked, start=1):
        print(f"  {rank}. threshold={value:g} (distribution error={scores[value]:.6f})")
    return [(value, paths[value], scores[value]) for value in ranked]


def _plot_threshold_outputs(
    ranked: Sequence[tuple[float, Path, float]], output_file: Path
) -> Path:
    """Save a compact orthogonal-slice comparison of ranked label volumes."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError(
            "Automatic threshold plots need matplotlib; install it with "
            "`pip install matplotlib`."
        ) from exc

    images = [nib.as_closest_canonical(nib.load(str(path))) for _, path, _ in ranked]
    shape = images[0].shape
    if any(image.shape != shape for image in images):
        raise ValueError("Selected NIfTI outputs must share a voxel grid to create a comparison plot")
    arrays = [np.rint(np.asarray(image.dataobj)).astype(np.int32) for image in images]
    occupied = np.zeros(shape, dtype=bool)
    for data in arrays:
        occupied |= data > 0
    coordinates = np.argwhere(occupied)
    if not len(coordinates):
        raise ValueError("Selected NIfTI outputs contain no labeled voxels to plot")
    center = np.rint((coordinates.min(axis=0) + coordinates.max(axis=0)) / 2).astype(int)
    views = ("Axial", "Coronal", "Sagittal")
    all_labels = np.concatenate([np.unique(data[data > 0]) for data in arrays])
    vmin, vmax = int(all_labels.min()), int(all_labels.max())

    fig, axes = plt.subplots(len(ranked), 3, figsize=(11, 3.4 * len(ranked)), squeeze=False)
    for row, ((threshold, _, score), data) in enumerate(zip(ranked, arrays)):
        slices = (
            data[:, :, center[2]].T,
            data[:, center[1], :].T,
            data[center[0], :, :].T,
        )
        for ax, slice_data, view in zip(axes[row], slices, views):
            shown = np.ma.masked_where(slice_data == 0, slice_data)
            ax.imshow(shown, cmap="nipy_spectral", vmin=vmin, vmax=max(vmax, vmin + 1), interpolation="nearest", origin="lower")
            ax.set_title(view)
            ax.set_axis_off()
        axes[row, 0].set_title(f"Threshold {threshold:g} | error {score:.4f}\nAxial")
    fig.suptitle("Top ribbon thresholds: cortical atlas label maps", y=1.01)
    fig.tight_layout()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_file, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_file


def cifti_to_volume(
    cifti_file: str | PathLike,
    output_dir: str | PathLike,
    *,
    subjects_dir: str | PathLike | None = None,
    reference_cache: str | PathLike | None = None,
    reference_url: str | None = None,
    source_subject: str = "fsaverage",
    target_subject: str = "MNI152NLin6Asym",
    target_density: str = "164k",
    threshold: float = 0.05,
    thresholds: Sequence[float] | str | None = None,
    reference_cifti: str | PathLike | None = None,
    reference_volume: str | PathLike | None = None,
    auto_thresholds: Sequence[float] = _AUTO_THRESHOLDS,
    mask_upper: float = 2.0,
    fwhm_mm: float = 2.0,
    nsteps: int = 10,
    neighborhood_mm: float = 2.0,
    maxiters: int = 4,
) -> Path | dict[float, Path]:
    """Convert a CIFTI dlabel to one or more merged label volumes.

    Uses NiBabel, SciPy, and neuromaps without invoking Workbench, FreeSurfer,
    or AFNI executables. Bundled registration surfaces and SUMA surfaces,
    ribbon masks, and M2M files are used by default; pass ``subjects_dir`` to
    use your own. Intermediate files are
    retained in ``output_dir``. ``threshold`` selects one run; ``thresholds``
    runs a sweep while reusing threshold-independent surface transforms.
    Returns a Path for one run or a threshold-to-Path dictionary for a sweep.
    """
    subjects_dir = (
        ensure_reference_files(reference_cache, reference_url)
        if subjects_dir is None else Path(subjects_dir).expanduser().resolve()
    )
    output_dir = Path(output_dir)
    suma_dir = subjects_dir / target_subject / "SUMA"
    automatic = isinstance(thresholds, str) and thresholds.lower() == "auto"
    if isinstance(thresholds, str) and not automatic:
        raise ValueError("thresholds as a string must be 'auto'")
    if reference_cifti is not None and reference_volume is not None:
        raise ValueError("Pass only reference_cifti; reference_volume is a deprecated alias")
    # Keep the previous keyword working for callers who passed their original
    # dlabel there; auto selection now reads CIFTI vertex counts, not a NIfTI.
    reference_cifti = reference_cifti or reference_volume or cifti_file
    single_run = thresholds is None
    threshold_values = (
        [float(threshold)] if single_run
        else [float(x) for x in (auto_thresholds if automatic else thresholds)]
    )
    if not threshold_values:
        raise ValueError("thresholds must contain at least one value")
    if not math.isfinite(mask_upper) or mask_upper < 0:
        raise ValueError("mask_upper must be a finite nonnegative number")
    if any(not math.isfinite(x) for x in threshold_values):
        raise ValueError("threshold values must be finite")
    if len(set(threshold_values)) != len(threshold_values):
        raise ValueError("threshold values must be unique")
    if any(x < 0 or x > mask_upper for x in threshold_values):
        raise ValueError("each threshold must be between 0 and mask_upper")
    if automatic and not Path(reference_cifti).is_file():
        raise FileNotFoundError(f"reference_cifti not found: {reference_cifti}")
    if automatic:
        _cifti_cortical_distribution(Path(reference_cifti))  # validate before the expensive conversion
    tags = [f"thr-{x:g}".replace(".", "p") for x in threshold_values]
    if len(set(tags)) != len(tags):
        raise ValueError("threshold values produce duplicate output folder names")
    if (
        not math.isfinite(fwhm_mm)
        or not math.isfinite(neighborhood_mm)
        or fwhm_mm < 0
        or nsteps < 1
        or neighborhood_mm < 0
        or maxiters < 0
    ):
        raise ValueError("invalid blur, sampling, or hole-filling parameter")

    required = [Path(cifti_file)]
    for hemi in ("lh", "rh"):
        required.extend((
            subjects_dir / source_subject / "surf" / f"{hemi}.sphere.reg",
            subjects_dir / target_subject / "surf" / f"{hemi}.sphere.reg",
            suma_dir / f"std.141.{target_subject}_{hemi}.niml.M2M",
            suma_dir / f"std.141.{hemi}.smoothwm.gii",
            suma_dir / f"std.141.{hemi}.pial.gii",
            suma_dir / f"{hemi}.ribbon.nii.gz",
        ))
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing pipeline input files:\n" + "\n".join(missing))

    try:
        from neuromaps.transforms import fslr_to_fslr, fslr_to_fsaverage
    except ImportError as exc:
        raise ImportError(
            "The end-to-end pipeline needs neuromaps; install it with "
            "`pip install surf2volume[pipeline]`."
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)

    left_cifti = output_dir / "left.cortex.label.gii"
    right_cifti = output_dir / "right.cortex.label.gii"
    subcortical = output_dir / "subcortical.nii"
    separate_cifti(cifti_file, left_cifti, right_cifti, subcortical)

    mapped_labels = {}
    for hemi, side, source_gifti in (
        ("lh", "L", left_cifti),
        ("rh", "R", right_cifti),
    ):
        fslr_164k = fslr_to_fslr(
            str(source_gifti), target_density=target_density,
            hemi=side, method="nearest",
        )[0]
        fsaverage_label = output_dir / f"{hemi}.fsaverage{target_density}.label.gii"
        fsaverage_image = fslr_to_fsaverage(
            fslr_164k, target_density=target_density,
            hemi=side, method="nearest",
        )[0]
        nib.save(fsaverage_image, str(fsaverage_label))

        target_label = output_dir / f"{hemi}.{target_subject}.label.gii"
        resample_surface_label(
            fsaverage_label, source_subject, target_subject, hemi,
            subjects_dir, target_label,
        )

        mapfile = suma_dir / f"std.141.{target_subject}_{hemi}.niml.M2M"
        mapped_label = output_dir / f"{hemi}.std141.label.gii"
        resample_gifti_with_m2m(target_label, mapfile, mapped_label)
        mapped_labels[hemi] = mapped_label

    outputs = {}
    blur_ready = set()
    for current_threshold, tag in zip(threshold_values, tags):
        threshold_dir = output_dir / tag
        threshold_dir.mkdir(parents=True, exist_ok=True)
        filled_volumes = {}

        for hemi in ("lh", "rh"):
            blur_file = output_dir / f"{hemi}.blur.ribbon.fwhm-{fwhm_mm:g}mm.nii.gz"
            first_use = hemi not in blur_ready
            filled = threshold_dir / f"{hemi}.filled.nii.gz"
            spackle_surface_to_volume(
                mapped_labels[hemi],
                suma_dir / f"std.141.{hemi}.smoothwm.gii",
                suma_dir / f"std.141.{hemi}.pial.gii",
                suma_dir / f"{hemi}.ribbon.nii.gz",
                filled,
                fwhm_mm=fwhm_mm,
                mask_range=(current_threshold, mask_upper),
                nsteps=nsteps,
                neighborhood_mm=neighborhood_mm,
                maxiters=maxiters,
                blurred_ribbon=blur_file if first_use else None,
                blurred_ribbon_input=None if first_use else blur_file,
            )
            blur_ready.add(hemi)
            filled_volumes[hemi] = filled

        merged = threshold_dir / f"{target_subject}_cortex_subcortex_merged.nii.gz"
        merge_label_volumes(
            filled_volumes["lh"], filled_volumes["rh"], subcortical, merged
        )
        outputs[current_threshold] = merged

    if automatic:
        selected_outputs = select_best_threshold(
            outputs, reference_cifti,
            top_n=3,
            report_file=output_dir / "auto_threshold_selection.json",
        )
        plot_path = _plot_threshold_outputs(
            selected_outputs, output_dir / "auto_threshold_top3.png"
        )
        print(f"Threshold comparison plot saved to: {plot_path}")
        return {value: path for value, path, _ in selected_outputs}
    return outputs[threshold_values[0]] if single_run else outputs
