#!/usr/bin/env bash

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
load_config "${1:-}"

require_file "${INPUT_CIFTI}"
require_command "${WB_COMMAND}"

echo "Separating cortical and subcortical CIFTI components"
"${WB_COMMAND}" -cifti-separate "${INPUT_CIFTI}" COLUMN \
    -label CORTEX_LEFT "${LEFT_CORTEX_GII}" \
    -label CORTEX_RIGHT "${RIGHT_CORTEX_GII}" \
    -volume-all "${SUBCORTICAL_NIFTI}"

require_file "${LEFT_CORTEX_GII}"
require_file "${RIGHT_CORTEX_GII}"
require_file "${SUBCORTICAL_NIFTI}"
echo "CIFTI separation complete: ${CIFTI_WORK_DIR}"

