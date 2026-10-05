# surf2volume

Python tools for separating CIFTI dlabel files and converting cortical labels to NIfTI, with no Workbench, FreeSurfer, or AFNI executable required for the Python pipeline.

## Install

```bash
pip install surf2volume
```
or
```
pip install -i https://test.pypi.org/simple/ surf2volume==0.2.0
```


## Convert CIFTI to NIfTI

```python
from surf2volume import cifti_to_volume

outputs = cifti_to_volume(
    cifti_file="atlas.dlabel.nii",
    output_dir="atlas_output",
    thresholds="auto",
)
```

When `subjects_dir` is omitted, required reference files are extracted from the installed package into `~/.cache/surf2volume/references-v1`. You can instead pass an existing FreeSurfer/SUMA subjects directory. `thresholds="auto"` ranks candidate ribbon thresholds using cortical parcel-size distributions in the source CIFTI and saves the top-three comparison image and score report.

The lower-level functions (`separate_cifti`, `resample_surface_label`, `resample_gifti_with_m2m`, `spackle_surface_to_volume`, and `merge_label_volumes`) are also directly available from `surf2volume`. `mri_surf2surf` remains a subprocess wrapper when command-level comparison is needed.

## Reference data and redistribution

The bundled archive contains FreeSurfer-derived fsaverage registration surfaces and locally generated MNI152NLin6Asym/SUMA reference files. Read [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and [`FREESURFER_LICENSE.txt`](FREESURFER_LICENSE.txt). The MNI/FSL template-derived assets require confirmation of their upstream redistribution terms before public release.
