#!/usr/bin/env bash
# Start the service: one API + CPU workers + one worker per NPU card.
#
# Usage:
#   cp deploy/host/.env.example .env   # then edit .env
#   bash deploy/host/start.sh
#
# Override the env file with ASCEND_OP_EVAL_ENV_FILE=/path/to/env bash deploy/host/start.sh
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/environment.sh"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ASCEND_OP_EVAL_ENV_FILE:-${ROOT_DIR}/.env}"

if [[ ! -r "${ENV_FILE}" ]]; then
  echo "Missing readable environment file: ${ENV_FILE}" >&2
  echo "Create it from ${ROOT_DIR}/deploy/host/.env.example and set site-specific values." >&2
  exit 2
fi

# Load .env (export every KEY=VALUE; comments/blank lines are ignored by the shell)
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/environment.sh"

source "${ROOT_DIR}/deploy/cann.sh"

PYTHON_BIN="${PYTHON_BIN:-python3}"
# Preflight: the engine is bundled by default; only validate an explicit override
if [[ -n "${ASCEND_OP_EVAL_ENGINE_DIR:-}" && ! -d "${ASCEND_OP_EVAL_ENGINE_DIR}" ]]; then
  echo "ASCEND_OP_EVAL_ENGINE_DIR is set but not a directory: '${ASCEND_OP_EVAL_ENGINE_DIR}'" >&2
  echo "Unset it to use the bundled engine (ascend_op_eval/engine)." >&2
  exit 2
fi

# Workers launch from the repository root; resolve their path-based interpreter
# there before probing from a temporary directory.
if [[ "${PYTHON_BIN}" == */* && "${PYTHON_BIN}" != /* ]]; then
  PYTHON_BIN="${ROOT_DIR}/${PYTHON_BIN}"
fi
# Host attempts execute from temporary directories. A sandbox owns its import
# context and may expose the package only inside that sandbox.
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/deployment_preflight.py" --engine-import-context
cd "${ROOT_DIR}"
export PYTHON_BIN
exec bash deploy/launch.sh all "${LOG_DIR:-logs}"
