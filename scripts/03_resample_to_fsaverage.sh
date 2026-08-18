#!/usr/bin/env bash

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
load_config "${1:-}"

require_file "${LEFT_CORTEX_GII}"
require_file "${RIGHT_CORTEX_GII}"
require_command "${PYTHON_BIN:-python3}"

"${PYTHON_BIN:-python3}" "${SCRIPT_DIR}/03_resample_to_fsaverage.py" \
    --left "${LEFT_CORTEX_GII}" \
    --right "${RIGHT_CORTEX_GII}" \
    --left-output "${LEFT_FSAVERAGE_GII}" \
    --right-output "${RIGHT_FSAVERAGE_GII}" \
    --density "${TARGET_DENSITY:-164k}"

