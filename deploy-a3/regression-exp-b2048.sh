#!/usr/bin/env bash
# Regression anchor: exp BLOCK=2048 kernel through the deployed cannbench-a3-2.0
# service (A2 anchor ev_136b000f8f394f02b61c2ecfd82f09e0, 18/18 on the 18-case
# set; the a3-2.0 aligned task set carries 20 cases — expect all-pass).
# reference_device_policy comes from conversion.json next to definition.json
# (npu-strict), read automatically by submit_eval.py.
set -euo pipefail

EVO=/home/n84449292/canada_group_dir/evo-cannbench
DEPLOY=/home/n84449292/canada_group_dir/kernel-design-agent/deploy-a3
URL=${EVALUATION_URL:-http://80.5.5.102:11907}

python3 "$EVO/adapter/submit_eval.py" verify \
  --url "$URL" \
  --capability-file "$HOME/.config/cannbench-evo/trial-token" \
  --definition "$EVO/tasks/exp/environment/inner-loop/definition.json" \
  --workloads "$EVO/tasks/exp/environment/inner-loop/workloads.jsonl" \
  --triton "$EVO/experiments/notes/triton-eval-a2-deploy-20261031/exp_triton_b2048.py" \
  --save-handle "$DEPLOY/regression-handle.json"
