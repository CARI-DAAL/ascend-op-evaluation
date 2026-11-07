---
status: current
applies_to: legacy-evaluation-and-custom-method-v1
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# 本地 issue tracker

本轮 ascend-op-eval 开发使用本地 Markdown，遵循 Matt to-tickets / implement-spec 的任务图流程。

- Feature spec：[spec](../plans/ascend-op-eval/spec.md)。
- 每张 issue：[issues 目录](../plans/ascend-op-eval/issues)，一个文件一张票。
- 依赖索引：[graph.json](../plans/ascend-op-eval/graph.json)。
- 状态与执行约定：[tracker README](../plans/ascend-op-eval/README.md)。
- 多 agent 入口：[implementation prompt](../plans/ascend-op-eval/implementation-prompt.md)。

新票的 triage 状态为 ready-for-agent；依赖满足后才能领取。主 agent 在合入和本票验收后标 done，Comments 追加讨论与阻塞。graph 不复制可变状态。

本配置只确定本 feature 的 tracker，不迁移或关闭已有 docs/plans JSON 计划，不发布远程 issues。后续 feature 可另行选择 tracker。
