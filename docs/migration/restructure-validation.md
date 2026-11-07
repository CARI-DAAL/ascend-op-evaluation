---
status: current
applies_to: repository-restructure
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# Repository restructure delivery and validation

Branch: `feat/ascend-op-eval-restructure`. Base: local main `e1dbe98`, which
includes fetched origin/main `a34ed59` and the subsequent 19 local main commits.
Validation below covers this branch's changed working tree on Python 3.12.3.

## Delivered

- Canonical product/distribution/namespace and process/client commands.
- Per-package metadata and src layout for server, client, compatibility bridge,
  default operator client adapter and external CANNBench method adapter.
- Control, execution, resource-health and runtime responsibilities in named
  server directories, with installed process entrypoints.
- Optional old Python imports sharing canonical class identities, old portable
  operator-plugin installation path and thin old launcher wrappers.
- Canonical environment prefixes, conflict checks and preserved durable
  namespaces/owner/volume identity.
- Current guides/reference/explanations, separate research/proposals, accepted
  glossary and formal AOE plans outside scratch. All 24 ticket IDs and dependency
  references remain present.
- Reproducible portable plugin generation, documentation validation and updated
  CI/release metadata paths. The CPU workflow file is renamed while its existing
  required-check display name is retained pending remote branch-protection changes.

The naming/cutover behavior and rollback procedure are in
[rename-and-cutover.md](rename-and-cutover.md).

## Checks

| Check | Result |
| --- | --- |
| Full CPU regression, `python -m pytest -m 'not npu' -q` | **2702 passed, 14 skipped, 7 deselected**, 138.68 seconds; one existing FastAPI/Starlette httpx deprecation warning |
| Focused deployment checks | 75 passed, including real Compose configuration rendering and isolated launcher execution |
| Post-metadata client/plugin/migration regressions | 29 passed |
| Five independent wheel builds | All succeeded |
| Fresh venv wheel install, outside repository cwd | All five distributions installed; client/server/worker/CANNBench-preparation help commands succeeded |
| Lightweight installed imports | Server HTTP and client import without Torch, torch_npu or Triton; wheel includes input-generation license and CANNBench method materials |
| Compatibility identity | Old settings, attempt-lease and sandbox imports share canonical class identity |
| Ruff, compileall, shell syntax | Passed |
| Release manifest declaration consistency | `consistent: true` |
| Portable plugin generation and documentation links | Passed |
| Formal plan graph | 24 files and dependency references present |

Skipped CPU-suite checks retain their existing environment requirements; they
are not counted as passed device or external-consumer validation. No NPU,
CANN compilation, profiler measurement or full upstream-harness qualification
was run for this migration.

## Separate functional and remote work

The built-in operator translator/evaluator/engine and task-specific caches remain
in the service until their AOE extraction tickets are implemented. The default
adapter is independently packaged on the caller side. Generic `/executions`,
artifact trees, isolated child execution and multi-card reservation remain planned;
this restructuring does not mark those functional tickets complete.

Remote repository renaming, publishing packages/plugins, production cutover,
independent package-tag publication and removal of still-needed compatibility
entries have not been performed. Existing service release automation continues
to use its reviewed `v*` tag stream and the relocated service metadata.
