---
status: current
applies_to: legacy-evaluation-and-custom-method-v1
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# Naming and compatibility rules

| Surface | Canonical name |
| --- | --- |
| Product / planned repository slug | Ascend Op Eval / `ascend-op-eval` |
| Service distribution / namespace | `ascend-op-eval` / `ascend_op_eval` |
| Client distribution / namespace | `ascend-op-eval-client` / `ascend_op_eval_client` |
| Operator client adapter | `ascend-op-eval-adapter-default` / `ascend_op_eval_adapter_default` |
| External CANNBench methods | `ascend-op-eval-adapter-cannbench` / `ascend_op_eval_adapter_cannbench` |
| Optional import bridge | `ascend-op-eval-compat` / `ascend_op_eval_compat` |
| User / process commands | `ascend-op-eval` / `ascend-op-eval-server` |
| Main plugin / adapter design kit | `ascend-op-eval` / `ascend-op-eval-adapter-kit` |
| Service settings | `ASCEND_OP_EVAL_*` |
| Client settings | `ASCEND_OP_EVAL_CLIENT_URL`, `ASCEND_OP_EVAL_CLIENT_CAPABILITY_FILE` |

Use kebab-case document/product paths, snake_case Python modules/functions/fields,
and PascalCase Python types. Use the [domain vocabulary](../../GLOSSARY.md):
evaluation, execution and attempt retain their distinct meanings. Use
`evaluation_profile` for task rules and `profiling` for diagnostic collection.

Service release, client release, adapter release, wire/storage versions,
method versions and content digests identify different things. Independent
packages need compatible contracts, not equal release numbers. Plugin manifests
agree with the client source they distribute. The existing wire/storage identity
is unchanged by the project rename.

## Retained old names

`TRITON_EVAL_*` is accepted for existing service settings, and `EVALUATION_URL` /
`EVALUATION_CAPABILITY_FILE` for clients. Conflicting old/new settings fail with
field names rather than secret values. Internal subprocess policies continue to
receive their existing keys while workers also export canonical names.

`triton-eval:v2.1`, `triton-eval-redis-v2`, existing PID-file identity, existing
capability/manifest paths and historical handles are durable compatibility data.
Keep their configured identity during upgrades. `plugins/triton-eval` is a
reproducibly generated compatibility distribution; its standalone client uses
the same source as the new plugin. `triton_evaluation` is available only through
the optional compatibility package, with documented old module aliases.

Upstream source names, license headers, historical commit URLs and immutable
fixtures keep their original spelling. The remote currently remains
`CARI-Fields/triton-op-evaluation`; owner-side repository renaming and redirects
are a separate operation from this branch.
