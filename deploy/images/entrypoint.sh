#!/usr/bin/env bash
# Initialize the mounted host CANN/driver and run the image's declared Python stack.
#
#   entrypoint.sh all       -> API + CPU workers + one NPU worker per configured card
#   entrypoint.sh api       -> configured API listeners only
#   entrypoint.sh workers   -> workers only
#   entrypoint.sh <cmd...>  -> exec cmd (escape hatch, e.g. `bash`)
#
# PYTHON_BIN selects the interpreter shared by the service and engine subprocesses.
set -euo pipefail
: "${PYTHON_BIN:=python3}"

# --- Host driver libs (mounted from host) ---
DRIVER_LIB="${ASCEND_DRIVER_PATH:-/usr/local/Ascend/driver}/lib64"
if [[ -d "${DRIVER_LIB}" ]]; then
  export LD_LIBRARY_PATH="${DRIVER_LIB}:${DRIVER_LIB}/driver:${LD_LIBRARY_PATH:-}"
fi

# CANN's set_env.sh preserves existing values, so clear inherited toolkit paths
# before initializing the host installation mounted into this container.
if [[ -n "${CANN_SET_ENV_PATH:-}" && -r "${CANN_SET_ENV_PATH}" ]]; then
  unset ASCEND_TOOLKIT_HOME ASCEND_HOME_PATH ASCEND_OPP_PATH \
        ASCEND_AICPU_PATH ASCEND_SLOG_PATH DAVINCIHOME 2>/dev/null || true
else
  echo "WARN: CANN_SET_ENV_PATH ('${CANN_SET_ENV_PATH:-unset}') not readable; " \
       "torch_npu / the engine will likely fail to import." >&2
fi

source /opt/ascend-op-eval/deploy/cann.sh

cd /opt/ascend-op-eval
source deploy/environment.sh

# --- Fail closed before API/workers: secret, build equality, bind ---
# The host preflight owns image/digest verification (no docker socket is mounted in the
# container by design); this boundary re-verifies everything reachable in-process.
verify_readiness() {
  "${PYTHON_BIN}" - <<'PYREADINESS'
import os
import sys

from ascend_op_eval.config import Settings
from ascend_op_eval.control.security import CapabilityRegistry

settings = Settings.from_env()
try:
    CapabilityRegistry.from_secret_file(settings.capability_secret_path)
except Exception:
    sys.exit("capability secret failed validation")

build = os.environ.get("ASCEND_OP_EVAL_EVALUATOR_BUILD", "")
image = os.environ.get("ASCEND_OP_EVAL_IMAGE", "")
git_sha = build.removeprefix("git:")
reviewed_git = (
    build.startswith("git:") and len(git_sha) == 40
    and all(char in "0123456789abcdef" for char in git_sha)
)
if build != settings.evaluator_build:
    sys.exit("evaluator build disagrees with the configured setting")
if image and build != image.rsplit("@", 1)[-1] and not reviewed_git:
    sys.exit("evaluator build must equal the immutable image's sha256 digest")

host = os.environ.get("ASCEND_OP_EVAL_API_HOST", "127.0.0.1")
allow_wildcard = os.environ.get("ASCEND_OP_EVAL_ALLOW_WILDCARD_BIND", "") == "1"
if not allow_wildcard and (host in ("0.0.0.0", "::") or ":" in host):
    sys.exit(
        "API host must be a single IPv4 address, never a wildcard "
        "(0.0.0.0 needs ASCEND_OP_EVAL_ALLOW_WILDCARD_BIND=1)"
    )
PYREADINESS
}

if [[ "${ASCEND_OP_EVAL_SKIP_READINESS:-}" != "1" ]]; then
  verify_readiness
fi

case "${1:-all}" in
  api|workers|all) exec bash deploy/launch.sh "${1:-all}" ;;
  *) exec "$@" ;;
esac
