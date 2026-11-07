# syntax=docker/dockerfile:1
# Ascend Op Eval worker image. The service package declares heavy dependencies.
# Build from the repository root; CANN and the driver are mounted at deployment.
ARG BASE_IMAGE=python:3.11
FROM ${BASE_IMAGE}

ARG PIP_EXTRA_INDEX_URL=""
ENV PYTHONUNBUFFERED=1
WORKDIR /opt/ascend-op-eval

# Cache the declared Ascend stack independently of source changes.
COPY packages/ascend-op-eval/pyproject.toml ./packages/ascend-op-eval/
RUN --mount=type=cache,target=/root/.cache/pip \
    mkdir -p packages/ascend-op-eval/src/ascend_op_eval \
 && touch packages/ascend-op-eval/src/ascend_op_eval/__init__.py \
 && pip install --retries 10 --timeout 120 \
      ${PIP_EXTRA_INDEX_URL:+--extra-index-url ${PIP_EXTRA_INDEX_URL}} \
      "./packages/ascend-op-eval[npu]"

COPY packages/ascend-op-eval ./packages/ascend-op-eval
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps ./packages/ascend-op-eval

COPY --chmod=755 deploy/images/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY deploy/environment.sh /opt/ascend-op-eval/deploy/environment.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["all"]
