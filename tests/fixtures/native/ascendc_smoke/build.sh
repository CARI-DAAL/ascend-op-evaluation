#!/usr/bin/env bash
set -eu
: "${ASCEND_HOME_PATH:?The worker must provide ASCEND_HOME_PATH and the ASC CMake package}"
cmake -S . -B build -DNPU_ARCH="${1:-dav-2201}" -DNATIVE_WRONG="${2:-OFF}"
cmake --build build --parallel 2
