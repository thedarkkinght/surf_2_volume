#!/usr/bin/env bash

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
load_config "${1:-}"

require_file "${TEMPLATE_T1}"
require_command "${RECON_ALL}"
require_command "${SUMA_MAKE_SPEC}"

prepared_t1="${WORK_DIR}/${SUBJECT_ID}_prepared_T1w.nii.gz"

if [[ "${ZERO_PAD_ENABLED:-1}" == "1" ]]; then
    require_command "${THREED_ZEROPAD}"
    echo "Zero-padding template: ${TEMPLATE_T1}"
    "${THREED_ZEROPAD}" \
        -prefix "${prepared_t1}" \
        -RL "${ZERO_PAD_RL:-256}" \
        -AP "${ZERO_PAD_AP:-256}" \
        -IS "${ZERO_PAD_IS:-256}" \
        "${TEMPLATE_T1}"
else
    echo "Zero-padding disabled; copying template into the work directory."
    cp "${TEMPLATE_T1}" "${prepared_t1}"
fi

export SUBJECTS_DIR

if [[ "${RUN_RECON_ALL:-1}" == "1" ]]; then
    echo "Running FreeSurfer reconstruction for ${SUBJECT_ID}"
    "${RECON_ALL}" -all -sd "${SUBJECTS_DIR}" -sid "${SUBJECT_ID}" -i "${prepared_t1}"
else
    echo "RUN_RECON_ALL=0; reusing ${SUBJECT_DIR}"
    require_dir "${SUBJECT_DIR}"
fi

echo "Creating SUMA specification files"
"${SUMA_MAKE_SPEC}" -NIFTI -sid "${SUBJECT_ID}"

require_dir "${SUMA_DIR}"
echo "Template preparation complete: ${SUMA_DIR}"

