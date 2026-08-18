#!/usr/bin/env bash

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
load_config "${1:-}"

require_command "${PYTHON_BIN:-python3}"

tag="$(threshold_tag "${GM_THRESHOLD}")"
left_fill="${SUMA_DIR}/lh.${ATLAS_NAME}.thr-${tag}.fill.nii.gz"
right_fill="${SUMA_DIR}/rh.${ATLAS_NAME}.thr-${tag}.fill.nii.gz"
merged_atlas="${OUTPUT_DIR}/${SUBJECT_ID}_cortex_subcortex_${ATLAS_NAME}_thr-${tag}.nii.gz"
gray_mask="${OUTPUT_DIR}/${SUBJECT_ID}_gray_matter_probability.nii.gz"

require_file "${left_fill}"
require_file "${right_fill}"
require_file "${SUBCORTICAL_NIFTI}"

"${PYTHON_BIN:-python3}" "${SCRIPT_DIR}/06_merge_atlas.py" \
    --left "${left_fill}" \
    --right "${right_fill}" \
    --subcortical "${SUBCORTICAL_NIFTI}" \
    --output "${merged_atlas}" \
    --priority "${MERGE_PRIORITY:-left-right-subcortical}"

"${PYTHON_BIN:-python3}" "${SCRIPT_DIR}/07_merge_gray_matter_mask.py" \
    --left "${SUMA_DIR}/lh.blur.ribbon.nii.gz" \
    --right "${SUMA_DIR}/rh.blur.ribbon.nii.gz" \
    --output "${gray_mask}"

echo "Atlas: ${merged_atlas}"
echo "Gray-matter probability mask: ${gray_mask}"
