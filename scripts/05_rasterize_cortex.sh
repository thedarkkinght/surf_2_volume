#!/usr/bin/env bash

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
load_config "${1:-}"

require_dir "${SUMA_DIR}"
require_command "${THREED_CALC}"
require_command "${THREED_MERGE}"
require_command "${SURF_TO_VOL_SPACKLE}"

left_ribbon="${SUMA_DIR}/lh.ribbon.nii"
right_ribbon="${SUMA_DIR}/rh.ribbon.nii"
require_file "${left_ribbon}"
require_file "${right_ribbon}"
require_file "${SUMA_DIR}/res.141.lh.${ATLAS_NAME}.niml.dset"
require_file "${SUMA_DIR}/res.141.rh.${ATLAS_NAME}.niml.dset"

left_float="${SUMA_DIR}/lh.fl.ribbon.nii.gz"
right_float="${SUMA_DIR}/rh.fl.ribbon.nii.gz"
left_blur="${SUMA_DIR}/lh.blur.ribbon.nii.gz"
right_blur="${SUMA_DIR}/rh.blur.ribbon.nii.gz"

"${THREED_CALC}" -a "${left_ribbon}" -datum float -prefix "${left_float}" -expr 'a'
"${THREED_MERGE}" -1blur_fwhm "${RIBBON_BLUR_FWHM:-2}" -doall -datum float \
    -prefix "${left_blur}" "${left_float}"

"${THREED_CALC}" -a "${right_ribbon}" -datum float -prefix "${right_float}" -expr 'a'
"${THREED_MERGE}" -1blur_fwhm "${RIBBON_BLUR_FWHM:-2}" -doall -datum float \
    -prefix "${right_blur}" "${right_float}"

tag="$(threshold_tag "${GM_THRESHOLD}")"
left_prefix="${SUMA_DIR}/lh.${ATLAS_NAME}.thr-${tag}.fill"
right_prefix="${SUMA_DIR}/rh.${ATLAS_NAME}.thr-${tag}.fill"
left_fill="${left_prefix}.nii.gz"
right_fill="${right_prefix}.nii.gz"

"${SURF_TO_VOL_SPACKLE}" \
    -spec "${SUMA_DIR}/std.141.${SUBJECT_ID}_lh.spec" \
    -surfA smoothwm \
    -surfB pial \
    -maskset "${left_blur}<${GM_THRESHOLD}..2>" \
    -surfset "${SUMA_DIR}/res.141.lh.${ATLAS_NAME}.niml.dset" \
    -mode \
    -prefix "${left_prefix}"

"${SURF_TO_VOL_SPACKLE}" \
    -spec "${SUMA_DIR}/std.141.${SUBJECT_ID}_rh.spec" \
    -surfA smoothwm \
    -surfB pial \
    -maskset "${right_blur}<${GM_THRESHOLD}..2>" \
    -surfset "${SUMA_DIR}/res.141.rh.${ATLAS_NAME}.niml.dset" \
    -mode \
    -prefix "${right_prefix}"

require_file "${left_fill}"
require_file "${right_fill}"
echo "Cortical rasterization complete at threshold ${GM_THRESHOLD}"
