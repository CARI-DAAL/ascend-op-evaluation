---
status: current
applies_to: legacy-evaluation-and-custom-method-v1
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# Ascend Op Eval documentation

Choose a current workflow below. The running instance's `/openapi.json` and
`/docs` describe its actual schemas. Proposed execution interfaces are listed
separately and are not commands available in the current release.

## Use

- [Evaluate an operator](guides/evaluate-an-operator.md)
- [Prepare inputs, submit and recover](guides/evaluations.md)
- [Native AscendC projects](guides/native-projects.md)
- [Custom checker, measurement and harness methods](guides/custom-methods.md)
- [Portable operator plugin](../plugins/ascend-op-eval/README.md)
- [Custom-method plugin](../plugins/custom-method-eval/README.md)

## Reference and explanation

- [Domain vocabulary](../GLOSSARY.md)
- [Naming and compatibility rules](reference/naming.md)
- [Implemented capabilities and qualification](reference/support-matrix.md)
- [Release identity](reference/release-identity.md)
- [Reference device policy](reference/reference-device-policy.md)
- [Current evaluation lifecycle](explanation/evaluation-lifecycle.md)
- [Attempt and physical-device provenance](explanation/execution-provenance.md)
- [Device health](explanation/device-health.md)
- [Isolation](explanation/execution-isolation.md)
- [Measurement evidence](explanation/measurement-evidence.md)

## Operate

- [Deployment](operations/deployment.md)
- [Recovery and upgrades](operations/recovery.md)
- [Naming and package cutover](migration/rename-and-cutover.md)
- [Restructure delivery and validation](migration/restructure-validation.md)
- [Profiler runtime preparation](operations/profiler-runtime.md)
- [Reference cache policies](operations/reference-cache.md)
- [Process labels](operations/process-labels.md)

## Develop and maintain

- [Contributing](../CONTRIBUTING.md)
- [Package layout and dependencies](development/package-layout.md)
- [Release workflow](development/releases.md)
- [Tests](../tests/README.md) and [NPU validation](development/npu-validation.md)
- [Supported repository scripts](../scripts/README.md)
- [Agent workflow](development/agent-workflow.md)
- [Implementation plans](plans/README.md)
- [Adapter design kit](../plugins/ascend-op-eval-adapter-kit/README.md)
- [Instance ownership decision](adr/0001-evaluation-instance-ownership.md)
- [Admission and evidence decision](adr/0002-admission-before-execution.md)

## Designs and evidence

- [Accepted repository restructuring proposal](proposals/ascend-op-eval-restructure/README.md)
- [Proposed execution core](proposals/execution-core/README.md) and [method responsibilities](proposals/execution-core/capabilities.md)
- [CANNBench method source review](research/cannbench-methods-review.md)
- [cannbot method source review](research/cannbot-methods-review.md)
- [AscendC support research](research/ascendc-support-assessment.md)
- [Verifier audit](research/verifier-audit.md)
- [Feedback performance experiments](research/feedback-performance.md)
- [Historical source snapshots](migration/history.md)
