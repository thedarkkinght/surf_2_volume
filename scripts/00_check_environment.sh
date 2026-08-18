#!/usr/bin/env bash

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
load_config "${1:-}"

require_file "${INPUT_CIFTI}"
require_file "${TEMPLATE_T1}"

for executable in \
    "${WB_COMMAND}" \
    "${RECON_ALL}" \
    "${MRI_SURF2SURF}" \
    "${SUMA_MAKE_SPEC}" \
    "${SURF_TO_SURF}" \
    "${SURF_TO_VOL_SPACKLE}" \
    "${THREED_ZEROPAD}" \
    "${THREED_CALC}" \
    "${THREED_MERGE}" \
    "${PYTHON_BIN:-python3}"; do
    require_command "${executable}"
done

"${PYTHON_BIN:-python3}" -c \
    'import nibabel, nilearn, neuromaps, numpy; print("Python imaging dependencies: OK")'

if [[ ! -e "${SUBJECTS_DIR}/fsaverage" ]]; then
    echo "Warning: ${SUBJECTS_DIR}/fsaverage is missing." >&2
    echo "Link or copy fsaverage before stage 4." >&2
fi

echo "Input CIFTI: ${INPUT_CIFTI}"
echo "Template T1: ${TEMPLATE_T1}"
echo "Subject ID: ${SUBJECT_ID}"
echo "Gray-matter threshold: ${GM_THRESHOLD}"
echo "Environment check complete"
