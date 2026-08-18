# Surf_2_Volume

Surf_2_Volume is a configurable workflow for converting a cortical-subcortical
CIFTI label atlas into a NIfTI volume. It combines Connectome Workbench,
neuromaps, FreeSurfer, AFNI/SUMA, and Python image processing. A blurred cortical
ribbon mask provides an adjustable constraint on the voxels eligible to receive
cortical labels.

The workflow was developed using the Cole-Anticevic Brain-wide Network Partition
(CAB-NP) and an MNI152NLin6Asym template. The scripts use configurable paths and
can be adapted to another compatible CIFTI atlas or template. A converted volume
is a derived representation for volume-based software and is not equivalent to
analysis in the native surface space.

## Workflow

1. Prepare the target T1-weighted template and run FreeSurfer reconstruction.
2. Generate the corresponding SUMA surfaces and standard `std.141` mesh.
3. Separate the input CIFTI file into left cortex, right cortex, and subcortex.
4. Resample cortical labels from fsLR to fsaverage with nearest-label mapping.
5. Transfer fsaverage labels to the target template surface.
6. Map the labels to the `std.141` mesh and fill voxels within a blurred cortical ribbon.
7. Resample cortical outputs to the subcortical grid and merge the components.

The default overlap priority reproduces the original implementation:

```text
left cortex > right cortex > subcortex
```

This priority can be changed in `scripts/06_merge_atlas.py` if subcortical labels
should take precedence in overlapping voxels.

## Repository layout

```text
.
├── config.example.env
├── requirements.txt
├── scripts/
│   ├── 00_check_environment.sh
│   ├── 01_prepare_template.sh
│   ├── 02_separate_cifti.sh
│   ├── 03_resample_to_fsaverage.py
│   ├── 03_resample_to_fsaverage.sh
│   ├── 04_map_to_template_surface.sh
│   ├── 05_rasterize_cortex.sh
│   ├── 06_merge_outputs.sh
│   ├── 06_merge_atlas.py
│   ├── 07_merge_gray_matter_mask.py
│   ├── resample_atlas_to_reference.py
│   └── run_pipeline.sh
└── output/
```

Input data and intermediate files are excluded from Git by default.

## Requirements

- Linux environment
- Connectome Workbench with `wb_command`
- FreeSurfer 7.4.1, including an accessible `fsaverage` subject
- AFNI and SUMA, including `3dZeropad`, `3dcalc`, `3dmerge`, `SurfToSurf`,
  `@SUMA_Make_Spec_FS`, and `@surf_to_vol_spackle`
- Python 3.9 or later
- Python packages listed in `requirements.txt`

FreeSurfer requires a valid license. Source the FreeSurfer and AFNI setup scripts
before running the workflow. The `fsaverage` subject must be present or linked at
`$SUBJECTS_DIR/fsaverage`.

## Input files

The example configuration expects:

- CAB-NP CIFTI label file:
  `CortexSubcortex_ColeAnticevic_NetPartition_wSubcorGSR_netassignments_LR.dlabel.nii`
- Target template:
  `tpl-MNI152NLin6Asym_res-01_T1w.nii.gz`

Place these files in `data/input/`, or set their absolute paths in `config.env`.
The source atlases and templates remain subject to their respective licenses and
terms of use.

## Installation

```bash
git clone https://github.com/thedarkkinght/surf_2_volume.git
cd surf_2_volume

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp config.example.env config.env
```

Edit `config.env` before continuing. In particular, set `PROJECT_ROOT`, input
paths, `SUBJECTS_DIR`, executable paths, and the intended gray-matter threshold.

## Run the complete pipeline

```bash
bash scripts/run_pipeline.sh config.env
```

The merged atlas and combined gray-matter probability mask are written to
`output/`. Intermediate surface and volume files are written to `work/`.

## Run individual stages

Each stage can also be run independently:

```bash
bash scripts/00_check_environment.sh config.env
bash scripts/01_prepare_template.sh config.env
bash scripts/02_separate_cifti.sh config.env
bash scripts/03_resample_to_fsaverage.sh config.env
bash scripts/04_map_to_template_surface.sh config.env
bash scripts/05_rasterize_cortex.sh config.env
bash scripts/06_merge_outputs.sh config.env
```

This is useful when testing different gray-matter thresholds. Change
`GM_THRESHOLD` in `config.env`, then rerun stages 5 and 6 rather than repeating
FreeSurfer reconstruction.

## Main parameters

| Parameter | Default | Meaning |
| --- | ---: | --- |
| `TARGET_DENSITY` | `164k` | fsLR and fsaverage target density |
| `RIBBON_BLUR_FWHM` | `2` | FWHM used to blur the cortical ribbon |
| `GM_THRESHOLD` | `0.25` | Lower bound applied to the blurred ribbon mask |
| `MERGE_PRIORITY` | `left-right-subcortical` | Precedence in overlapping voxels |
| `RUN_RECON_ALL` | `1` | Run or reuse the template FreeSurfer reconstruction |
| `ZERO_PAD_ENABLED` | `1` | Apply the original AFNI zero-padding step |

### Note on zero-padding

The original commands used:

```bash
3dZeropad -RL 256 -AP 256 -IS 256
```

In AFNI, `-RL`, `-AP`, and `-IS` add or cut planes symmetrically so that the
resulting volume has the requested number of slices in the respective anatomical
directions. Thus, the command above targets 256 slices in each direction; it does
not add 256 slices at every edge. Confirm that a 256-slice field of view is
appropriate for the selected template. If zero-padding is unnecessary, set
`ZERO_PAD_ENABLED=0`.

## Gray-matter mask

The cortical ribbon is converted to floating point and blurred with a 2 mm FWHM
kernel by default. `@surf_to_vol_spackle` then fills voxels whose blurred-ribbon
values fall between `GM_THRESHOLD` and 2.

`scripts/07_merge_gray_matter_mask.py` combines the left and right blurred masks
using the voxelwise maximum and preserves floating-point values. It does not
round the probability-like mask to integers. To create a binary mask explicitly:

```bash
python scripts/07_merge_gray_matter_mask.py \
  --left work/freesurfer_subjects/MNI152NLin6Asym/surf/SUMA/lh.blur.ribbon.nii.gz \
  --right work/freesurfer_subjects/MNI152NLin6Asym/surf/SUMA/rh.blur.ribbon.nii.gz \
  --binary-threshold 0.25 \
  --output output/MNI152NLin6Asym_gray_matter_thr-0p25.nii.gz
```

## Optional resampling to an analysis grid

Use nearest-neighbor interpolation for label atlases and write to a new file:

```bash
python scripts/resample_atlas_to_reference.py \
  --atlas output/MNI152NLin6Asym_cortex_subcortex_ColeAnticevic_thr-0p25.nii.gz \
  --reference /path/to/reference_image.nii.gz \
  --output output/ColeAnticevic_on_reference_grid.nii.gz
```

The script rejects attempts to overwrite the source atlas.

## Quality-control recommendations

Before using a converted atlas:

1. Confirm the NIfTI affine, orientation, voxel size, and target template.
2. Verify that labels remain integers after all resampling operations.
3. Inspect cortical coverage and assignments outside the intended gray matter.
4. Inspect cortical-subcortical overlap, especially when changing merge priority.
5. Record the CIFTI atlas version, template version, software versions, and exact
   `GM_THRESHOLD` used for the released file.

The current comparison is descriptive and does not establish that one threshold
or mapping method is optimal for every atlas or downstream analysis.

## Data and software availability

Precomputed CAB-NP volumes can be placed in `output/` for release. For files too
large for ordinary Git, use Git LFS or a versioned data repository and record a
persistent identifier in this README.

## Citation

If you use this workflow, cite the associated Surf_2_Volume manuscript and the
source atlas. Add the final manuscript citation and DOI here after publication.

## License

No software license is assigned by this template. Before public release, choose
and add a license that is compatible with the included code and all redistributed
data. Third-party software and atlas files retain their own licenses.
