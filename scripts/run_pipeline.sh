#!/usr/bin/env bash

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
config_file="${1:-${REPO_ROOT}/config.env}"
load_config "${config_file}"

"${SCRIPT_DIR}/00_check_environment.sh" "${config_file}"
"${SCRIPT_DIR}/01_prepare_template.sh" "${config_file}"
"${SCRIPT_DIR}/02_separate_cifti.sh" "${config_file}"
"${SCRIPT_DIR}/03_resample_to_fsaverage.sh" "${config_file}"
"${SCRIPT_DIR}/04_map_to_template_surface.sh" "${config_file}"
"${SCRIPT_DIR}/05_rasterize_cortex.sh" "${config_file}"
"${SCRIPT_DIR}/06_merge_outputs.sh" "${config_file}"

echo "Pipeline complete"
