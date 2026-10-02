"""Pure-Python application of SUMA M2M nearest-node maps."""

from copy import deepcopy
import re
from os import PathLike
from pathlib import Path

import nibabel as nib
import numpy as np
from nibabel.gifti import GiftiImage
from scipy import ndimage, stats


def _niml_int_array(path: Path, name: str) -> np.ndarray:
    content = path.read_bytes()
    match = re.search(rb"<" + name.encode() + rb"\b([^>]*)>", content)
    if match is None:
        raise ValueError(f"{path} does not contain NIML element {name}")
    attrs = match.group(1)
    if not re.search(rb'ni_type="int"', attrs):
        raise ValueError(f"NIML element {name} must contain integers")
    size = re.search(rb'ni_dimen="(\d+)"', attrs)
    if size is None:
        raise ValueError(f"NIML element {name} has no ni_dimen")
    start = match.end()
    end = content.find(b"</" + name.encode() + b">", start)
    if end < 0:
        raise ValueError(f"NIML element {name} is not closed")
    expected = int(size.group(1))
    raw = content[start:end]
    if len(raw) != expected * 4:
        raise ValueError(f"NIML element {name} has an unexpected binary size")
    return np.frombuffer(raw, dtype="<i4")


def _afni_fir_blur(data: np.ndarray, fwhm_mm: float, voxel_sizes: np.ndarray) -> np.ndarray:
    """Approximate AFNI's short-radius Gaussian FIR and mirrored edges."""
    sigma = fwhm_mm / np.sqrt(8 * np.log(2))
    result = np.asarray(data, dtype=np.float32).copy()
    if sigma == 0:
        return result
    for axis, spacing in enumerate(voxel_sizes):
        radius = max(1, int(np.ceil(2.5 * sigma / spacing)))
        scale = spacing / sigma
        step = scale / 22.0  # AFNI integrates each voxel bin with 11 subdivisions.
        weights = np.empty(radius + 1, dtype=np.float64)
        for offset in range(radius + 1):
            x = offset * scale + np.arange(-11, 12) * step
            samples = np.exp(-0.5 * x * x)
            samples[0] *= 0.5
            samples[-1] *= 0.5
            weights[offset] = samples.sum()
        weights /= weights[0] + 2 * weights[1:].sum()
        kernel = np.r_[weights[:0:-1], weights].astype(np.float32)
        result = ndimage.convolve1d(result, kernel, axis=axis, mode="mirror")
    return result


def resample_gifti_with_m2m(
    source_dset: str | PathLike,
    mapfile: str | PathLike,
    output: str | PathLike,
) -> Path:
    """Apply a SUMA M2M map's ``NearestNode`` mapping to GIFTI data.

    This uses the first source neighbor stored for each mapped target node,
    matching ``SurfToSurf -output_params NearestNode`` without running AFNI.
    The output remains GIFTI; the source label table and array metadata are kept.
    """
    mapfile = Path(mapfile)
    header = mapfile.read_bytes().split(b">", 1)[0]
    counts = re.search(rb'M1_N_Nodes="(\d+)"', header)
    source_count = re.search(rb'M2_N_Nodes="(\d+)"', header)
    if counts is None or source_count is None:
        raise ValueError(f"{mapfile} is not a SUMA M2M map with node counts")
    target_count, source_count = int(counts.group(1)), int(source_count.group(1))

    target_nodes = _niml_int_array(mapfile, "M1n")
    neighbor_counts = _niml_int_array(mapfile, "M2Nne_M1n")
    neighbors = _niml_int_array(mapfile, "M2ne_M1n").reshape(-1, 3)[:, 0]
    if len(target_nodes) != len(neighbor_counts) or len(neighbors) != len(target_nodes):
        raise ValueError(f"{mapfile} contains inconsistent mapping arrays")
    if np.any(target_nodes < 0) or np.any(target_nodes >= target_count):
        raise ValueError(f"{mapfile} contains an out-of-range target node")

    source_image = nib.load(str(source_dset))
    if not isinstance(source_image, GiftiImage):
        raise ValueError("source_dset must be a GIFTI file")
    if not source_image.darrays or any(
        array.data.ndim != 1 or len(array.data) != source_count
        for array in source_image.darrays
    ):
        raise ValueError("GIFTI data length does not match M2_N_Nodes in the mapfile")

    result = deepcopy(source_image)
    mapped = (neighbor_counts > 0) & (neighbors >= 0)
    target_nodes = target_nodes[mapped]
    source_nodes = neighbors[mapped]
    for source_array, result_array in zip(source_image.darrays, result.darrays):
        values = np.asarray(source_array.data)
        target_values = np.zeros(target_count, dtype=values.dtype)
        target_values[target_nodes] = values[source_nodes]
        result_array.data = target_values
        result_array.dims = list(target_values.shape)
        result_array.coordsys = None
    nib.save(result, str(output))
    return Path(output)


def spackle_surface_to_volume(
    surface_data: str | PathLike,
    smoothwm: str | PathLike,
    pial: str | PathLike,
    ribbon: str | PathLike,
    output: str | PathLike,
    *,
    fwhm_mm: float = 2.0,
    mask_range: tuple[float, float] = (0.05, 2.0),
    nsteps: int = 10,
    extension: float = 0.1,
    neighborhood_mm: float = 2.0,
    maxiters: int = 4,
    blurred_ribbon: str | PathLike | None = None,
    blurred_ribbon_input: str | PathLike | None = None,
) -> Path:
    """Project surface values between two surfaces and fill the ribbon volume.

    Pure-Python approximation of ``3dcalc`` + ``3dmerge -1blur_fwhm`` +
    ``@surf_to_vol_spackle``. ``surface_data`` may be a one-value-per-vertex
    GIFTI or an AFNI/SUMA NIML ``.niml.dset`` (such as SurfToSurf output).
    The two pointset GIFTIs must use the ribbon's world coordinates. Returns
    the filled NIfTI path. AFNI is not invoked.
    """
    if nsteps < 1 or maxiters < 0 or fwhm_mm < 0 or neighborhood_mm < 0:
        raise ValueError("nsteps/maxiters and distances must be nonnegative (nsteps > 0)")
    lower, upper = mask_range
    if lower > upper:
        raise ValueError("mask_range lower bound must not exceed upper bound")

    ribbon_image = nib.load(str(ribbon))
    voxel_sizes = nib.affines.voxel_sizes(ribbon_image.affine)
    if blurred_ribbon_input is not None:
        if blurred_ribbon is not None:
            raise ValueError("Use blurred_ribbon to write a blur or blurred_ribbon_input to reuse one")
        blur_image = nib.load(str(blurred_ribbon_input))
        if blur_image.shape != ribbon_image.shape or not np.allclose(blur_image.affine, ribbon_image.affine):
            raise ValueError("Precomputed blurred ribbon must match the ribbon volume grid")
        blurred = np.asarray(blur_image.dataobj, dtype=np.float32)
    else:
        data = ribbon_image.get_fdata(dtype=np.float32)
        blurred = _afni_fir_blur(data, fwhm_mm, voxel_sizes)
        if blurred_ribbon is not None:
            blur_image = nib.Nifti1Image(blurred, ribbon_image.affine, ribbon_image.header.copy())
            nib.save(blur_image, str(blurred_ribbon))
    mask = (blurred >= lower) & (blurred <= upper)

    def pointset(path):
        image = nib.load(str(path))
        for array in image.darrays:
            if array.intent == nib.nifti1.intent_codes.code["NIFTI_INTENT_POINTSET"]:
                return np.asarray(array.data, dtype=np.float64)
        raise ValueError(f"No GIFTI pointset found in {path}")

    surface_data = Path(surface_data)
    if surface_data.name.endswith(".niml.dset"):
        labels = _niml_int_array(surface_data, "SPARSE_DATA")
    else:
        data_image = nib.load(str(surface_data))
        if not isinstance(data_image, GiftiImage) or not data_image.darrays:
            raise ValueError("surface_data must be a GIFTI or NIML dataset")
        data_array = next(
            (array for array in data_image.darrays
             if array.intent == nib.nifti1.intent_codes.code["NIFTI_INTENT_LABEL"]),
            data_image.darrays[0],
        )
        labels = np.asarray(data_array.data).squeeze()
    if labels.ndim != 1:
        raise ValueError("surface_data must contain one value per vertex")
    labels = labels.astype(np.int32)
    points_a, points_b = pointset(smoothwm), pointset(pial)
    if len(points_a) != len(points_b) or len(labels) != len(points_a):
        raise ValueError(
            "surface_data, smoothwm, and pial must have matching vertex counts; "
            f"got {len(labels)}, {len(points_a)}, and {len(points_b)}. "
            "For SurfToSurf output, pass its .niml.dset file, not the lower-density input GIFTI."
        )

    # Sample slightly beyond both surfaces; approximate AFNI -f_p1_fr/-f_pn_fr.
    fractions = np.linspace(-extension, 1 + extension, nsteps)
    world = points_a[:, None, :] + fractions[None, :, None] * (points_b - points_a)[:, None, :]
    ijk = nib.affines.apply_affine(np.linalg.inv(ribbon_image.affine), world.reshape(-1, 3))
    ijk = np.floor(ijk + 0.5).astype(np.int64)
    shape = np.asarray(mask.shape)
    inside = np.all((ijk >= 0) & (ijk < shape), axis=1)
    ijk = ijk[inside]
    vertex = np.broadcast_to(np.arange(len(points_a))[:, None], (len(points_a), nsteps)).ravel()[inside]
    step = np.broadcast_to(np.arange(nsteps), (len(points_a), nsteps)).ravel()[inside]
    linear = np.ravel_multi_index(ijk.T, mask.shape)
    in_mask = mask.ravel()[linear]

    # Approximate -stop_gap and -f_index voxels.
    valid = np.zeros(len(linear), dtype=bool)
    order = np.lexsort((step, vertex))
    last_vertex, seen_mask, stopped = -1, False, False
    for idx in order:
        current = vertex[idx]
        if current != last_vertex:
            last_vertex, seen_mask, stopped = current, False, False
        if stopped:
            continue
        if in_mask[idx]:
            seen_mask, valid[idx] = True, True
        elif seen_mask:
            stopped = True
    pair_key = vertex[valid].astype(np.int64) * np.prod(mask.shape) + linear[valid]
    _, first = np.unique(pair_key, return_index=True)
    vote_voxels = linear[valid][first]
    vote_values = labels[vertex[valid][first]]
    result = np.zeros(mask.shape, dtype=np.int32)
    nonzero = vote_values != 0
    if np.any(nonzero):
        stride = int(vote_values.max()) + 1
        pairs = vote_voxels[nonzero].astype(np.int64) * stride + vote_values[nonzero]
        unique, counts = np.unique(pairs, return_counts=True)
        voxels, values = unique // stride, unique % stride
        order = np.lexsort((values, -counts, voxels))
        voxels, values = voxels[order], values[order]
        first = np.r_[True, voxels[1:] != voxels[:-1]]
        result.ravel()[voxels[first]] = values[first]

    bounds = np.ceil(neighborhood_mm / voxel_sizes).astype(int)
    offsets = np.array([
        (x, y, z)
        for x in range(-bounds[0], bounds[0] + 1)
        for y in range(-bounds[1], bounds[1] + 1)
        for z in range(-bounds[2], bounds[2] + 1)
        if (x * voxel_sizes[0]) ** 2 + (y * voxel_sizes[1]) ** 2
        + (z * voxel_sizes[2]) ** 2 <= neighborhood_mm**2 + 1e-8
    ])
    for _ in range(maxiters):
        holes = np.argwhere(mask & (result == 0))
        if not len(holes):
            break
        neighbors = np.full((len(holes), len(offsets)), np.nan, dtype=np.float32)
        for j, offset in enumerate(offsets):
            coords = holes + offset
            valid_coords = np.all((coords >= 0) & (coords < shape), axis=1)
            rows = np.flatnonzero(valid_coords)
            values = result[coords[valid_coords, 0], coords[valid_coords, 1], coords[valid_coords, 2]]
            neighbors[rows, j] = np.where(values != 0, values, np.nan)
        has_neighbor = np.any(np.isfinite(neighbors), axis=1)
        modes = np.full(len(holes), np.nan, dtype=np.float32)
        modes[has_neighbor] = stats.mode(
            neighbors[has_neighbor], axis=1, nan_policy="omit", keepdims=False
        ).mode
        fill = np.isfinite(modes)
        result[holes[fill, 0], holes[fill, 1], holes[fill, 2]] = modes[fill].astype(np.int32)
        if not np.any(fill):
            break

    header = ribbon_image.header.copy()
    header.set_data_dtype(np.int16)
    nib.save(nib.Nifti1Image(result.astype(np.int16), ribbon_image.affine, header), str(output))
    return Path(output)
