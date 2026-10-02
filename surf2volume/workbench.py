"""Pure-Python operations for CIFTI files."""

from pathlib import Path
from os import PathLike
from xml.etree import ElementTree as ET

import nibabel as nib
import numpy as np
from nibabel.cifti2 import cifti2_axes
from nibabel.gifti import GiftiDataArray, GiftiImage, GiftiLabel, GiftiLabelTable


def _label_table(label_axis):
    """Combine per-map CIFTI label tables and return key remaps for each map."""
    combined = {}
    remaps = []
    next_key = 0
    for labels in label_axis.label:
        remap = {}
        for key, (name, rgba) in labels.items():
            color = tuple(float(x) for x in rgba)
            value = (name, color)
            if key in combined and combined[key] != value:
                while next_key in combined:
                    next_key += 1
                out_key = next_key
                next_key += 1
            else:
                out_key = key
            combined[out_key] = value
            remap[int(key)] = int(out_key)
        remaps.append(remap)
    table = GiftiLabelTable()
    for key, (name, rgba) in combined.items():
        label = GiftiLabel(key=key, red=rgba[0], green=rgba[1], blue=rgba[2], alpha=rgba[3])
        label.label = name
        table.labels.append(label)
    return table, remaps


def _surface_label(data, brain_axis, label_axis, structure, output):
    structure_mask = brain_axis.name == structure
    if not np.any(structure_mask):
        raise ValueError(f"CIFTI does not contain {structure}")
    n_vertices = brain_axis.nvertices[structure]
    vertices = brain_axis.vertex[structure_mask]
    values = np.floor(data[:, structure_mask] + 0.5).astype(np.int32)
    table, remaps = _label_table(label_axis)
    unassigned = next((label.key for label in table.labels if label.label == "???"), None)
    if unassigned is None:
        unassigned = 0 if all(label.key != 0 for label in table.labels) else max(
            (label.key for label in table.labels), default=-1
        ) + 1
        label = GiftiLabel(key=unassigned, red=0, green=0, blue=0, alpha=0)
        label.label = "???"
        table.labels.append(label)
    full = np.full((n_vertices, data.shape[0]), unassigned, dtype=np.int32)
    full[vertices, :] = values.T

    for map_index, remap in enumerate(remaps):
        col = full[vertices, map_index]
        for key, out_key in remap.items():
            col[values[map_index] == key] = out_key

    image = GiftiImage(labeltable=table)
    for map_index in range(full.shape[1]):
        image.add_gifti_data_array(
            GiftiDataArray(data=full[:, map_index], intent="NIFTI_INTENT_LABEL")
        )
    nib.save(image, str(output))


def _subcortical_label(data, brain_axis, label_axis, output):
    volume_mask = brain_axis.volume_mask
    has_volume_geometry = brain_axis.volume_shape is not None and brain_axis.affine is not None
    if has_volume_geometry:
        shape = tuple(int(x) for x in brain_axis.volume_shape)
        affine = brain_axis.affine
    else:
        # A cortical-only dlabel has no volume axis. Emit a harmless zero
        # placeholder so callers that merge cortex and subcortex can use the
        # same pipeline for cortical-only and whole-brain atlases.
        shape = (1, 1, 1)
        affine = np.eye(4)
    volume = np.zeros((*shape, data.shape[0]), dtype=np.int32)
    if has_volume_geometry and np.any(volume_mask):
        voxels = brain_axis.voxel[volume_mask]
        maps = np.floor(data[:, volume_mask] + 0.5).astype(np.int32)
        volume[voxels[:, 0], voxels[:, 1], voxels[:, 2], :] = maps.T
    if volume.shape[3] == 1:
        volume = volume[..., 0]
    image = nib.Nifti1Image(volume, affine)
    image.header.set_data_dtype(np.int32)
    if isinstance(label_axis, cifti2_axes.LabelAxis):
        image.header.set_intent("label")
        root = ET.Element("CaretExtension")
        for index, labels in enumerate(label_axis.label):
            info = ET.SubElement(root, "VolumeInformation", Index=str(index))
            label_table = ET.SubElement(info, "LabelTable")
            for key, (name, rgba) in labels.items():
                ET.SubElement(
                    label_table,
                    "Label",
                    Key=str(key), Red=str(rgba[0]), Green=str(rgba[1]),
                    Blue=str(rgba[2]), Alpha=str(rgba[3]),
                ).text = name
            ET.SubElement(info, "Type").text = "Label"
        image.header.extensions.append(
            nib.nifti1.Nifti1Extension(30, ET.tostring(root, encoding="utf-8"))
        )
    nib.save(image, str(output))


def separate_cifti(
    cifti_file: str | PathLike,
    left_label: str | PathLike = "left.ColeAnticevic.label.gii",
    right_label: str | PathLike = "right.ColeAnticevic.label.gii",
    subcortical_volume: str | PathLike = "subcortical.nii",
) -> tuple[Path, Path, Path]:
    """Separate cortex labels and subcortical voxels from a CIFTI dlabel.

    Writes the left/right surface label files and full-grid subcortical NIfTI,
    matching the requested ``-cifti-separate ... COLUMN`` operation without
    requiring Connectome Workbench. Requires NiBabel.
    """
    image = nib.load(str(cifti_file))
    if len(image.shape) != 2:
        raise ValueError("Only two-dimensional CIFTI files are supported")
    brain_axis = image.header.get_axis(1)
    label_axis = image.header.get_axis(0)
    if not isinstance(brain_axis, cifti2_axes.BrainModelAxis):
        raise ValueError("CIFTI COLUMN axis must describe brain models")
    if not isinstance(label_axis, cifti2_axes.LabelAxis):
        raise ValueError("CIFTI ROW axis must contain label maps")

    data = np.asanyarray(image.dataobj)
    _surface_label(data, brain_axis, label_axis, "CIFTI_STRUCTURE_CORTEX_LEFT", left_label)
    _surface_label(data, brain_axis, label_axis, "CIFTI_STRUCTURE_CORTEX_RIGHT", right_label)
    _subcortical_label(data, brain_axis, label_axis, subcortical_volume)
    return Path(left_label), Path(right_label), Path(subcortical_volume)
