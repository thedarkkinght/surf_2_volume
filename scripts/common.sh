#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

load_config() {
    local config_file="${1:-${REPO_ROOT}/config.env}"
    if [[ ! -f "${config_file}" ]]; then
        echo "Configuration file not found: ${config_file}" >&2
        echo "Copy config.example.env to config.env and edit it first." >&2
        exit 2
    fi

    export PROJECT_ROOT="${PROJECT_ROOT:-${REPO_ROOT}}"
    set -a
    # shellcheck disable=SC1090
    source "${config_file}"
    set +a

    : "${INPUT_CIFTI:?INPUT_CIFTI is required}"
    : "${TEMPLATE_T1:?TEMPLATE_T1 is required}"
    : "${SUBJECT_ID:?SUBJECT_ID is required}"
    : "${SUBJECTS_DIR:?SUBJECTS_DIR is required}"
    : "${ATLAS_NAME:?ATLAS_NAME is required}"
    : "${GM_THRESHOLD:?GM_THRESHOLD is required}"

    export WORK_DIR="${PROJECT_ROOT}/work"
    export CIFTI_WORK_DIR="${WORK_DIR}/cifti"
    export SURFACE_WORK_DIR="${WORK_DIR}/surface"
    export OUTPUT_DIR="${PROJECT_ROOT}/output"
    export SUBJECT_DIR="${SUBJECTS_DIR}/${SUBJECT_ID}"
    export SUMA_DIR="${SUBJECT_DIR}/surf/SUMA"

    export LEFT_CORTEX_GII="${CIFTI_WORK_DIR}/left.${ATLAS_NAME}.label.gii"
    export RIGHT_CORTEX_GII="${CIFTI_WORK_DIR}/right.${ATLAS_NAME}.label.gii"
    export SUBCORTICAL_NIFTI="${CIFTI_WORK_DIR}/subcortical.nii.gz"
    export LEFT_FSAVERAGE_GII="${SURFACE_WORK_DIR}/lh.${ATLAS_NAME}.fsaverage.label.gii"
    export RIGHT_FSAVERAGE_GII="${SURFACE_WORK_DIR}/rh.${ATLAS_NAME}.fsaverage.label.gii"

    mkdir -p "${WORK_DIR}" "${CIFTI_WORK_DIR}" "${SURFACE_WORK_DIR}" "${OUTPUT_DIR}" "${SUBJECTS_DIR}"
}

require_file() {
    local file_path="$1"
    if [[ ! -f "${file_path}" ]]; then
        echo "Required file not found: ${file_path}" >&2
        exit 2
    fi
}

require_dir() {
    local dir_path="$1"
    if [[ ! -d "${dir_path}" ]]; then
        echo "Required directory not found: ${dir_path}" >&2
        exit 2
    fi
}

require_command() {
    local command_name="$1"
    if ! command -v "${command_name}" >/dev/null 2>&1; then
        echo "Required command is unavailable: ${command_name}" >&2
        exit 2
    fi
}

threshold_tag() {
    local threshold="$1"
    printf '%s' "${threshold}" | tr '.' 'p'
}

