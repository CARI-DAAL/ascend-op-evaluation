#!/usr/bin/env bash
# Deploy the cannbench-a3-2.0 eval service on host A3 (80.5.5.102, 910B1x8,
# driver 26.1.1, host CANN 9.2.0 at /usr/local/Ascend/cann-9.2.0; the legacy
# cann910_B030 dir is a compat shim — cann-9.1.0 -> cann-9.2.0 plus a
# relocated-path set_env.sh — so CANN_SET_ENV_PATH below still resolves).
#
# Modelled on A2's restart-triton-eval-a32-t360.sh + docker/compose.yaml contract
# (see experiments/notes/triton-eval-a2-deploy-20261031/README.md in evo-cannbench).
# Machine-specific deltas vs A2:
#   - redis is the already-running host-net container on 127.0.0.1:6391 (db7)
#   - API binds this host's address 80.5.5.102
#   - shared box: cards 0,1,2,3,4
#   - full stack lives on python3.12 -> PYTHON_BIN=python3 (A2 used /usr/bin/python3)
#   - host CANN 9.1.0 has 910b ops, mounted at /opt/cann (A2 used image-internal)
set -euo pipefail

REPO=/home/n84449292/canada_group_dir/kernel-design-agent
IMAGE=triton-eval:a3-2.0-t360
GIT_SHA=72d89d84ca69fcc0a1d09b68b7d4190a2cda82e2   # cannbench-a3-2.0 branch tip

docker rm -f triton-eval >/dev/null 2>&1 || true

docker run -d --name triton-eval \
  --entrypoint /usr/local/bin/entrypoint.sh \
  --network host --ipc shareable --privileged --shm-size 32g \
  --restart unless-stopped \
  -e PYTHON_BIN=python3 \
  -e HOME=/tmp \
  -e TRITON_EVAL_REDIS_URL=redis://127.0.0.1:6391/7 \
  -e TRITON_EVAL_REDIS_PREFIX=triton-eval:v2.1 \
  -e TRITON_EVAL_API_HOST=80.5.5.102 \
  -e TRITON_EVAL_API_PORT=11907 \
  -e TRITON_EVAL_CARDS=0,1,2,3,4 \
  -e TRITON_EVAL_CPU_WORKERS=1 \
  -e TRITON_EVAL_DEVICE_HOLD_MB=64 \
  -e TRITON_EVAL_IMAGE="${IMAGE}" \
  -e TRITON_EVAL_EVALUATOR_BUILD="git:${GIT_SHA}" \
  -e TRITON_EVAL_RELEASE_MODE=release \
  -e TRITON_EVAL_RELEASE_MANIFEST=/opt/triton-eval/release-manifest.json \
  -e TRITON_EVAL_REFERENCE_DEVICE_POLICY=cpu-first \
  -e TRITON_EVAL_REFERENCE_DIAGNOSTICS_DIR=/opt/triton-eval/logs/reference-diagnostics \
  -e TRITON_EVAL_CAPABILITY_SECRET_PATH=/run/secrets/triton-eval \
  -e TRITON_EVAL_WORKER_HARDWARE_MODEL=Ascend910B1 \
  -e TRITON_EVAL_WORKER_DRIVER_VERSION=26.1.1 \
  -e TRITON_EVAL_WORKER_RUNTIME_VERSION=CANN-9.2.0 \
  -e TRITON_EVAL_WORKER_TOOLCHAIN_VERSION='CANN 9.2.0 / python 3.12.13 / torch 2.10.0 / torch_npu 2.10.0 / triton_ascend 3.6.0' \
  -e CANN_SET_ENV_PATH=/opt/cann/cann910_B030/cann-9.1.0/set_env.sh \
  -e ASCEND_DRIVER_PATH=/usr/local/Ascend/driver \
  -v /usr/local/Ascend:/opt/cann:ro \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi \
  -v /etc/ascend_install.info:/etc/ascend_install.info \
  -v "${REPO}/logs":/opt/triton-eval/logs \
  -v "${REPO}/deploy-a3/release-manifest-bound.json":/opt/triton-eval/release-manifest.json:ro \
  -v "${REPO}/.secrets/caller-token.json":/run/secrets/triton-eval:ro \
  "${IMAGE}" all

echo "deployed; logs: docker logs -f triton-eval"
