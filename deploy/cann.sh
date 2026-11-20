# Source from host and container launchers after selecting the CANN installation.
if [[ -n "${CANN_SET_ENV_PATH:-}" && -r "${CANN_SET_ENV_PATH}" ]]; then
  set +u
  source "${CANN_SET_ENV_PATH}"
  set -u
fi

# Some CANN installations keep libhccl.so in the architecture-specific directory.
if [[ -n "${CANN_SET_ENV_PATH:-}" ]]; then
  _cann_toolkit_dir="$(dirname "$(readlink -f "${CANN_SET_ENV_PATH}")")"
  for _archlib in "${_cann_toolkit_dir}/aarch64-linux/lib64" "${_cann_toolkit_dir}/lib64"; do
    if [[ -d "${_archlib}" && ":${LD_LIBRARY_PATH:-}:" != *":${_archlib}:"* ]]; then
      export LD_LIBRARY_PATH="${_archlib}:${LD_LIBRARY_PATH:-}"
    fi
  done
  unset _cann_toolkit_dir _archlib
fi
