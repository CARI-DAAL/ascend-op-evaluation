#!/usr/bin/env bash
# Replace the A3 container using its existing Redis instance and caller registry.
set -euo pipefail

profile="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "${profile}/../.." && pwd)"
env_file="${ASCEND_OP_EVAL_ENV_FILE:-${profile}/.env}"
manifest="${ASCEND_OP_EVAL_RELEASE_MANIFEST_HOST:-${profile}/release-manifest-bound.json}"
capabilities="${ASCEND_OP_EVAL_CAPABILITY_SECRET_PATH:-${root}/.secrets/caller-token.json}"
sandbox="${profile}/engine-sandbox.json"

for input in "${env_file}" "${manifest}" "${capabilities}" "${sandbox}"; do
  if [[ ! -f "${input}" || ! -r "${input}" ]]; then
    echo "Missing readable A3 deployment file: ${input}" >&2
    exit 2
  fi
done
sandbox_digest="$(sha256sum < "${sandbox}")"
image_identity="$(python3 - "${manifest}" <<'PYMANIFEST'
import json
import re
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    manifest = json.load(source)
image = manifest.get("image_reference")
if not isinstance(image, str) or not re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", image):
    sys.exit("A3 release manifest requires an immutable image reference")
if manifest.get("evaluator_build") != image.rsplit("@", 1)[1]:
    sys.exit("A3 release manifest build differs from the image digest")
print(image)
PYMANIFEST
)"
digest="${image_identity##*@}"
image="${image_identity}"
if ! docker image inspect "${image}" >/dev/null 2>&1; then
  # An offline build can be bound to its local image ID before registry publication.
  image="${digest}"
  docker image inspect "${image}" >/dev/null
fi
if docker container inspect triton-eval >/dev/null 2>&1; then
  docker rm -f triton-eval >/dev/null
fi

exec docker run -d --name triton-eval \
  --entrypoint /usr/local/bin/entrypoint.sh \
  --network host --ipc shareable --privileged --shm-size 32g \
  --restart unless-stopped \
  --env-file "${env_file}" \
  -e PYTHON_BIN=python3 \
  -e HOME=/tmp \
  -e ASCEND_OP_EVAL_IMAGE="${image_identity}" \
  -e ASCEND_OP_EVAL_EVALUATOR_BUILD="${digest}" \
  -e ASCEND_OP_EVAL_RELEASE_MODE=release \
  -e ASCEND_OP_EVAL_RELEASE_MANIFEST=/opt/ascend-op-eval/release-manifest.json \
  -e ASCEND_OP_EVAL_REFERENCE_DIAGNOSTICS_DIR=/opt/ascend-op-eval/logs/reference-diagnostics \
  -e ASCEND_OP_EVAL_CAPABILITY_SECRET_PATH=/run/secrets/ascend-op-eval \
  -e ASCEND_OP_EVAL_ENGINE_SANDBOX_CONFIG=/opt/ascend-op-eval/engine-sandbox.json \
  -e ASCEND_OP_EVAL_ENGINE_SANDBOX_SHA256="${sandbox_digest%% *}" \
  -e ASCEND_OP_EVAL_STAGE_SPOOL_DIR=/opt/ascend-op-eval/stage-spool \
  -v /usr/local/Ascend:/opt/cann:ro \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi \
  -v /etc/ascend_install.info:/etc/ascend_install.info \
  -v "${root}/logs":/opt/ascend-op-eval/logs \
  -v "${manifest}":/opt/ascend-op-eval/release-manifest.json:ro \
  -v "${sandbox}":/opt/ascend-op-eval/engine-sandbox.json:ro \
  -v "${capabilities}":/run/secrets/ascend-op-eval:ro \
  -v "${capabilities}":/run/secrets/triton-eval:ro \
  "${image}" all
