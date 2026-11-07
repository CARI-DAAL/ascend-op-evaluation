---
status: current
applies_to: legacy-evaluation-and-custom-method-v1
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# Ascend Op Eval naming and package cutover

This change renames the project and Python namespace, introduces independently
installable packages, reorganizes documentation and moves deployment materials.
It retains existing operator/custom-method HTTP contracts, durable record
meaning, owner recovery, Redis prefix and data-volume identity. It adds no
`/executions` wire contract.

## Before upgrading an existing instance

1. Record the existing owner URL, Redis endpoint/prefix, actual Compose project
   name, mounted volume name, secrets, release manifest and artifact locations.
   Use `docker compose ls`, the existing rendered configuration and volume
   inspection; do not infer a project name from the new checkout directory.
2. Stop new submissions at the existing routing/caller layer and drain work
   with the matching old workers. Save recovery handles and complete the normal
   backup procedure. Do not relabel queued work to a different evaluator build.
3. Install the new service package in a separate environment or build the new
   image. Rebuild deployment-specific sandbox/runtime source pins and generate
   a new release manifest for the actual new source/image digest. Old source
   pins are expected to fail after helper paths change.
4. Translate setting names using the table below. Preserve configured secret,
   cache and artifact paths. For Compose, explicitly set
   `ASCEND_OP_EVAL_COMPOSE_PROJECT_NAME` to the **actual old project name**.
   The retained logical volume `triton-eval-redis-v2` and prefix
   `triton-eval:v2.1` select existing state; renaming them is a separate data
   migration. Never use `down --volumes` as part of this upgrade.
5. Render the new Compose configuration and compare Redis/volume/owner
   identities before starting. The service key becomes `ascend-op-eval` while
   the Redis service and data identity remain the same. After draining, stop
   the old service container explicitly; do not leave an orphan old API/worker
   competing with the replacement on the same port/cards.
6. Start verified matching API/workers at the original owner URL. Recover a
   retained historical handle, replay a retained idempotency key, and submit a
   new request. Inspect actual evidence and runtime identity before reopening
   traffic. Perform target-device qualification separately.

Fresh installations may use the new project name from
[the Compose example](../../deploy/compose/.env.example). An existing installation
must replace that example value with its recorded project name.

## Names and entrypoints

| Old | Canonical | Compatibility |
| --- | --- | --- |
| root `pip install .` | `pip install ./packages/ascend-op-eval` | Root pyproject now configures tools only |
| `triton_evaluation` | `ascend_op_eval` | Optional ascend-op-eval-compat package aliases old modules |
| `.service.*` | `.control.*` | Optional old-namespace bridge |
| `.runtime.worker`, cache/evidence/process helpers | `.execution.*` | Optional old-namespace bridge |
| `.runtime.health` | `.resources.health` | Optional old-namespace bridge |
| `.runtime.sandbox`, profiler_runtime, execution_environment | `.runtimes.*` | Optional old-namespace bridge |
| repository API/worker scripts | `ascend-op-eval-server api`, `ascend-op-eval-server worker --cpu` or `--card N` | Existing scripts wrap installed entrypoints |
| `plugins/triton-eval` | `plugins/ascend-op-eval` | Generated old plugin remains usable |
| `triton_eval.py` | `ascend_op_eval.py`, or installed `ascend-op-eval` | Old plugin script retained |
| `plugins/eval-adapter-kit` | `plugins/ascend-op-eval-adapter-kit` | Update plugin installation location |
| `docker/` | `deploy/images/`, `deploy/compose/` | Update explicit deployment file paths |
| host/Compose launchers under scripts | `deploy/host/`, `deploy/compose/` | Old script paths are thin wrappers |
| `.scratch/ascend-op-eval` | `docs/plans/ascend-op-eval` | One canonical task state; IDs/dependencies retained |

```bash
python -m pip install ./packages/ascend-op-eval
# Only when an existing Python consumer still imports the old namespace:
python -m pip install ./packages/ascend-op-eval-compat
# Client/operator dependencies are independent of the server:
python -m pip install ./packages/ascend-op-eval-client ./adapters/default
```

Python compatibility aliases preserve class/exception identity. They do not
synthesize a new execution record or interpret an old result as method evidence.
Existing wire IDs remain `evaluation_id`; domain vocabulary for proposed generic
executions does not rename persisted fields.

## Settings

| Old | Canonical |
| --- | --- |
| `TRITON_EVAL_<FIELD>` | `ASCEND_OP_EVAL_<FIELD>` |
| `EVALUATION_URL` | `ASCEND_OP_EVAL_CLIENT_URL` |
| `EVALUATION_CAPABILITY_FILE` | `ASCEND_OP_EVAL_CLIENT_CAPABILITY_FILE` |

Existing service/client settings remain accepted. The Python settings model
compares parsed values when both prefixes are supplied and rejects a conflict
using setting names only. Shell launchers require matching representations when
both names are present; prefer configuring a single canonical name. Explicit
false and zero remain values, not absence.

Keep vendor-controlled settings such as `CANN_SET_ENV_PATH`, `MSPROF_BIN` and
`ASCEND_RT_VISIBLE_DEVICES` unchanged. Existing subprocess policies retain their
old keys; workers supply their validated values and canonical aliases together.

## Delivery scope and later functional work

The current change completes the naming, package installation, current method
adapter packaging, documentation and deployment-layout transition. The service
still bundles its existing operator translator/evaluator/engine and their
compatibility model. The default external package currently owns caller-side
format handling. This preserves behavior while establishing canonical packages.

Generic execution records, worker-side default-adapter extraction, artifact
trees, independent build/execute handoff, isolated child executions and atomic
multi-card reservations are existing AOE functional tickets. They remain
proposed and require their original CPU/device/parity acceptance gates. See
[package responsibilities](../development/package-layout.md) and the
[support matrix](../reference/support-matrix.md).

The remote repository is still `CARI-Fields/triton-op-evaluation`; remote
renaming, plugin reinstallation, publication and production rollout have not
been performed by a local source branch. Existing service `v*` release tags
remain readable. Package-qualified independent publishing is separately tracked.

## Rollback and compatibility removal

Retain the old image/environment, its source-pinned policies and original
release manifest. Rollback uses the original owner, prefix and volume, and only
runs after draining replacement workers and checking that the old decoder can
read records created during the cutover. Do not fabricate provenance or copy
new fields into historical records to make this check pass.

Remove aliases only after callers have migrated, old-plugin use has been checked,
the retention/recovery commitment has elapsed and a removal release has been
announced. Historical handles and source/fixture attribution remain intact.
