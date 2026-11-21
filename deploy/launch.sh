#!/usr/bin/env bash
# Start the selected processes in the prepared host or image environment.
set -euo pipefail

mode="${1:?expected api, workers or all}"
log_dir="${2:-}"
python_bin="${PYTHON_BIN:-python3}"
if [[ "${python_bin}" == */* ]]; then
  # CANN's profiler runs python3 by name from its export directory.
  python_dir="$(CDPATH= cd -- "$(dirname -- "${python_bin}")" && pwd)"
  export PATH="${python_dir}:${PATH}"
fi
api=(-m ascend_op_eval.entrypoints.run_api)
case "${mode}" in
  api) exec "${python_bin}" "${api[@]}" ;;
  workers|all) ;;
  *) echo "Unknown launch mode: ${mode}" >&2; exit 2 ;;
esac

cpu_count="${ASCEND_OP_EVAL_CPU_WORKERS:-1}"
if [[ ! "${cpu_count}" =~ ^([0-9]|[12][0-9]|3[0-2])$ ]]; then
  echo "ASCEND_OP_EVAL_CPU_WORKERS must be an integer from 0 to 32" >&2
  exit 2
fi
card_list="${ASCEND_OP_EVAL_CARDS:-0}"
card_list="${card_list//[[:space:]]/}"
if [[ ! "${card_list}" =~ ^[0-9,]*$ ]]; then
  echo "ASCEND_OP_EVAL_CARDS must contain nonnegative card IDs" >&2
  exit 2
fi
IFS=',' read -ra cards <<< "${card_list}"

pids=()
start() {
  local name="$1"
  shift
  echo "Starting ${name}" >&2
  if [[ -n "${log_dir}" ]]; then
    "${python_bin}" "$@" >"${log_dir}/${name}.log" 2>&1 &
  else
    "${python_bin}" "$@" &
  fi
  pids+=("$!")
}

stop() {
  kill "${pids[@]}" 2>/dev/null || true
  wait || true
  exit 0
}
trap stop TERM INT
if [[ -n "${log_dir}" ]]; then
  mkdir -p "${log_dir}"
fi

if [[ "${mode}" == all ]]; then
  start api "${api[@]}"
fi
worker=(-m ascend_op_eval.entrypoints.run_worker)
for ((i=0; i<cpu_count; i++)); do
  start "worker_cpu_${i}" "${worker[@]}" --cpu
done
for card in "${cards[@]}"; do
  [[ -z "${card}" ]] || start "worker_${card}" "${worker[@]}" --card "${card}"
done
if ((${#pids[@]} == 0)); then
  echo "No workers configured" >&2
  exit 2
fi
if [[ -n "${log_dir}" ]]; then
  printf '%s\n' "${pids[@]}" > "${log_dir}/triton-eval.pids"
  trap 'rm -f "${log_dir}/triton-eval.pids"' EXIT
fi
wait
