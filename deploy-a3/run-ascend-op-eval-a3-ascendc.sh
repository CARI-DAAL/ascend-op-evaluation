#!/usr/bin/env bash
# Deploy the ascend-op-eval service (custom-method-v1 + native AscendC) on host A3
# (80.5.5.102, 910B1x8, driver 26.1.1, host CANN 9.2.0 at /usr/local/Ascend/cann-9.2.0;
# the legacy cann910_B030 dir is a compat shim — cann-9.1.0 -> cann-9.2.0 plus a
# relocated-path set_env.sh — so CANN_SET_ENV_PATH below still resolves).
#
# Successor of run-triton-eval-a32-t360.sh (commit 6d08fca): same redis
# (127.0.0.1:6391 db7, prefix triton-eval:v2.1 — preserves evaluation history,
# idempotency keys and baseline cache), same API address 80.5.5.102:11907, same
# container name (evo-cannbench env_check greps for it), new image built from
# ascend-op-eval main. Capability file is mounted at BOTH the new canonical path
# (/run/secrets/ascend-op-eval) and the legacy path (/run/secrets/triton-eval)
# so existing env_check / adapter tooling keeps working unchanged.
#
# Cards: 0,1,3,4 — card 2 is occupied by another user's job; 5-7 host vllm services.
set -euo pipefail

REPO=/home/n84449292/canada_group_dir/projects/ascend-op-eval
IMAGE=ascend-op-eval:a3-2.0-ascendc
IMAGE_DIGEST=sha256:133cc8d4e42498c57e9751aa3dc9b67e496a91545edec59aba1c26c78141d3db

docker rm -f triton-eval >/dev/null 2>&1 || true

docker run -d --name triton-eval \
  --entrypoint /usr/local/bin/entrypoint.sh \
  --network host --ipc shareable --privileged --shm-size 32g \
  --restart unless-stopped \
  -e PYTHON_BIN=python3 \
  -e HOME=/tmp \
  -e ASCEND_OP_EVAL_REDIS_URL=redis://127.0.0.1:6391/7 \
  -e ASCEND_OP_EVAL_REDIS_PREFIX=triton-eval:v2.1 \
  -e ASCEND_OP_EVAL_API_HOST=80.5.5.102 \
  -e ASCEND_OP_EVAL_API_PORT=11907 \
  -e ASCEND_OP_EVAL_CARDS=0,1,3,4 \
  -e ASCEND_OP_EVAL_CPU_WORKERS=1 \
  -e ASCEND_OP_EVAL_DEVICE_HOLD_MB=64 \
  -e ASCEND_OP_EVAL_TRIAL_MAX_INFLIGHT=12 \
  -e ASCEND_OP_EVAL_SESSION_MAX_INFLIGHT=12 \
  -e ASCEND_OP_EVAL_IMAGE="ascend-op-eval@${IMAGE_DIGEST}" \
  -e ASCEND_OP_EVAL_EVALUATOR_BUILD="${IMAGE_DIGEST}" \
  -e ASCEND_OP_EVAL_RELEASE_MODE=release \
  -e ASCEND_OP_EVAL_RELEASE_MANIFEST=/opt/ascend-op-eval/release-manifest.json \
  -e ASCEND_OP_EVAL_REFERENCE_DEVICE_POLICY=cpu-first \
  -e ASCEND_OP_EVAL_REFERENCE_DIAGNOSTICS_DIR=/opt/ascend-op-eval/logs/reference-diagnostics \
  -e ASCEND_OP_EVAL_CAPABILITY_SECRET_PATH=/run/secrets/ascend-op-eval \
  -e ASCEND_OP_EVAL_METHOD_CAPABILITIES='["python","npu","process-isolation","soc-ascend910_93"]' \
  -e ASCEND_OP_EVAL_ENGINE_SANDBOX_CONFIG=/opt/ascend-op-eval/engine-sandbox.json \
  -e ASCEND_OP_EVAL_ENGINE_SANDBOX_SHA256="$(sha256sum "${REPO}/deploy-a3/engine-sandbox-a3.json" | cut -d' ' -f1)" \
  -e ASCEND_OP_EVAL_STAGE_SPOOL_DIR=/opt/ascend-op-eval/stage-spool \
  -e ASCEND_OP_EVAL_WORKER_HARDWARE_MODEL=Ascend910B1 \
  -e ASCEND_OP_EVAL_WORKER_DRIVER_VERSION=26.1.1 \
  -e ASCEND_OP_EVAL_WORKER_RUNTIME_VERSION=CANN-9.2.0 \
  -e ASCEND_OP_EVAL_WORKER_TOOLCHAIN_VERSION='CANN 9.2.0 / python 3.12.13 / torch 2.10.0+cpu / torch_npu 2.10.0 / triton_ascend 3.6.0' \
  -e CANN_SET_ENV_PATH=/opt/cann/cann910_B030/cann-9.1.0/set_env.sh \
  -e ASCEND_DRIVER_PATH=/usr/local/Ascend/driver \
  -v /usr/local/Ascend:/opt/cann:ro \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi \
  -v /etc/ascend_install.info:/etc/ascend_install.info \
  -v "${REPO}/logs":/opt/ascend-op-eval/logs \
  -v "${REPO}/deploy-a3/release-manifest-bound.json":/opt/ascend-op-eval/release-manifest.json:ro \
  -v "${REPO}/deploy-a3/engine-sandbox-a3.json":/opt/ascend-op-eval/engine-sandbox.json:ro \
  -v "${REPO}/.secrets/caller-token.json":/run/secrets/ascend-op-eval:ro \
  -v "${REPO}/.secrets/caller-token.json":/run/secrets/triton-eval:ro \
  "${IMAGE}" all

echo "deployed; logs: docker logs -f triton-eval"
