#!/usr/bin/env bash

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
load_config "${1:-}"

require_file "${LEFT_FSAVERAGE_GII}"
require_file "${RIGHT_FSAVERAGE_GII}"
require_dir "${SUMA_DIR}"
require_command "${MRI_SURF2SURF}"
require_command "${SURF_TO_SURF}"

if [[ ! -e "${SUBJECTS_DIR}/fsaverage" ]]; then
    echo "fsaverage is not available under SUBJECTS_DIR: ${SUBJECTS_DIR}/fsaverage" >&2
    echo "Copy or symlink it from the FreeSurfer installation before continuing." >&2
    exit 2
fi

export SUBJECTS_DIR

left_target="${SUMA_DIR}/lh.${ATLAS_NAME}.gii"
right_target="${SUMA_DIR}/rh.${ATLAS_NAME}.gii"

"${MRI_SURF2SURF}" \
    --srcsubject fsaverage \
    --trgsubject "${SUBJECT_ID}" \
    --sval "${LEFT_FSAVERAGE_GII}" \
    --tval "${left_target}" \
    --mapmethod nnf \
    --hemi lh

"${MRI_SURF2SURF}" \
    --srcsubject fsaverage \
    --trgsubject "${SUBJECT_ID}" \
    --sval "${RIGHT_FSAVERAGE_GII}" \
    --tval "${right_target}" \
    --mapmethod nnf \
    --hemi rh

pushd "${SUMA_DIR}" >/dev/null

"${SURF_TO_SURF}" \
    -i_gii std.141.lh.smoothwm.gii \
    -i_gii lh.smoothwm.gii \
    -prefix res.141.lh \
    -mapfile "std.141.${SUBJECT_ID}_lh.niml.M2M" \
    -dset "lh.${ATLAS_NAME}.gii" \
    -output_params NearestNode

"${SURF_TO_SURF}" \
    -i_gii std.141.rh.smoothwm.gii \
    -i_gii rh.smoothwm.gii \
    -prefix res.141.rh \
    -mapfile "std.141.${SUBJECT_ID}_rh.niml.M2M" \
    -dset "rh.${ATLAS_NAME}.gii" \
    -output_params NearestNode

left_generated="res.141.lh.lh.${ATLAS_NAME}.niml.dset"
right_generated="res.141.rh.rh.${ATLAS_NAME}.niml.dset"
left_final="res.141.lh.${ATLAS_NAME}.niml.dset"
right_final="res.141.rh.${ATLAS_NAME}.niml.dset"

require_file "${left_generated}"
require_file "${right_generated}"
mv -f "${left_generated}" "${left_final}"
mv -f "${right_generated}" "${right_final}"

popd >/dev/null
echo "Template-surface mapping complete: ${SUMA_DIR}"

