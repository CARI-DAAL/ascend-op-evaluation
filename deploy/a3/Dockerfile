# A3 offline overlay for the local Python 3.12 / Ascend stack.
FROM triton-eval:local

# --- purge the base's old checkout before overlaying ---
# The legacy base carries /opt/triton-eval (old layout); stale modules would
# poison digests and shadow entrypoints. Everything needed is COPY'd fresh.
RUN rm -rf /opt/triton-eval

WORKDIR /opt/ascend-op-eval

# --- service package + deployment materials (release manifest digests the
#     installed site-packages copy, which is byte-identical to these sources) ---
COPY packages/ascend-op-eval ./packages/ascend-op-eval
COPY deploy/images/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY deploy/environment.sh deploy/cann.sh deploy/launch.sh ./deploy/

# The offline base supplies transitive dependencies. Upgrade only the service's direct pins.
COPY deploy/a3/wheels/pins /tmp/pins/
RUN pip3 install --no-index --no-deps --no-build-isolation ./packages/ascend-op-eval \
 && python3 -c "from importlib.metadata import requires; print('\n'.join(r for r in requires('ascend-op-eval') if ';' not in r))" > /tmp/service-pins.txt \
 && pip3 install --no-cache-dir --no-deps --no-index --find-links /tmp/pins -r /tmp/service-pins.txt \
 && rm -rf /tmp/pins /tmp/service-pins.txt

# --- candidate wheel-build tooling (cannbench build.sh contract) ---
COPY deploy/a3/wheels/pybuild /tmp/pybuild/
RUN pip3 install --no-cache-dir --no-deps --no-index --find-links /tmp/pybuild \
      build==1.6.1 pyproject_hooks==1.3.3 \
 && rm -rf /tmp/pybuild

# --- worker runtime alignment (cannbench harness REQUIRED_RUNTIME_PACKAGES) ---
# torch_npu 2.10.0.post4 is the official-runner pin (worker-packages.json must
# declare exactly this); the remaining four are imported by the upstream
# harness but absent from the vllm-derived base.
COPY deploy/a3/wheels/npupost4 /tmp/npuwheels/
RUN pip3 install --no-cache-dir --no-deps --no-index \
      /tmp/npuwheels/torch_npu-2.10.0.post4-cp312-cp312-manylinux_2_28_aarch64.whl \
 && pip3 install --no-cache-dir --no-deps --no-index \
      /tmp/npuwheels/ml_dtypes-0.5.1-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl \
      /tmp/npuwheels/tornado-6.6-cp311-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl \
      /tmp/npuwheels/expecttest-0.3.0-py3-none-any.whl \
      /tmp/npuwheels/ruamel_yaml-0.19.1-py3-none-any.whl \
 && rm -rf /tmp/npuwheels

# --- bwrap (engine process-isolation sandbox) ---
# openEuler 0.4.1 binary (supports --die-with-parent/--clearenv/--cap-drop);
# its libselinux/libcap/libpcre2-8 deps are already in the ubuntu base.
# bwrap-ascend is a front-end that rewrites --dev-bind char devices to fresh
# root-owned nodes so the capability-free user-namespace child can open them
# (host Ascend nodes are 1000:1000 660; userns caps never reach init-ns
# devtmpfs). The engine sandbox manifest sets executable=/usr/bin/bwrap-ascend.
COPY deploy/a3/wheels/bwrap-bin /usr/bin/bwrap.real
COPY deploy/a3/bwrap-ascend.py /usr/bin/bwrap-ascend
RUN chmod 755 /usr/bin/bwrap.real /usr/bin/bwrap-ascend && bwrap.real --version

# --- named service identity (informational; service runs as root) ---
# The driver on this host rejects non-root NPU ioctls, so the service stays
# root and the sandbox device problem is solved by bwrap-ascend above. The
# passwd entry documents the deployer uid for auditing.
RUN getent group 1000 >/dev/null || groupadd -g 1000 HwHiAiUsers \
 && getent passwd 1006 >/dev/null || useradd -u 1006 -g 1000 -M -d /tmp -s /usr/sbin/nologin evalworker

# --- triton-ascend 3.6.0 (official-runner alignment) ---
COPY deploy/a3/wheels/triton_ascend-3.6.0-*.whl /tmp/t360/
RUN pip3 uninstall -y triton triton-ascend 2>/dev/null || true; \
    rm -rf /usr/local/lib/python3.12/site-packages/triton \
           /usr/local/lib/python3.12/site-packages/triton-*dist-info; \
    pip3 install --no-cache-dir --no-deps --force-reinstall \
      /tmp/t360/triton_ascend-3.6.0-*.whl \
 && rm -rf /tmp/t360 \
 && TORCH_DEVICE_BACKEND_AUTOLOAD=0 python3 -c "import importlib.metadata as md; assert md.version('triton-ascend') == '3.6.0'"
