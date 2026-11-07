# 06: worker 故障后恢复同一逻辑执行

**ID:** AOE-06

**What to build:** worker 或存储短暂故障后，调用方仍能恢复原任务及各 attempt 的证据，不会读到旧 attempt 覆盖的新结果。

**Blocked by:** AOE-03, AOE-05

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 执行契约与持久化

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

默认一次 attempt；仅在显式有限策略下重试基础设施故障。不承诺物理执行 exactly-once。

## Acceptance criteria

- [ ] 每次 attempt 有独立工作区、设备归属、事件和产物，旧 attempt 不能提交进度、引用或终态。
- [ ] 基础设施重试沿用冻结的规范请求、输入和 runtime 要求以及总 deadline，保留完整 attempt 历史。
- [ ] 正常非零退出、程序 signal、wrong 报告和缺报告不会触发寻找成功结果的自动重试。
- [ ] 租约过期与实际停止分离；未确认旧程序清理的资源隔离，不能并行授予新 attempt。
- [ ] 恢复中输入引用、artifact 封存、终态提交和 GC 的部分失败不产生虚假完成或悬空可用产物。
- [ ] 旧 owner handle、幂等关系与新 execution 存储版本隔离；解码历史记录不改写历史 provenance。

## Validation

用故障注入和隔离 Redis 演练 claim 后崩溃、封存后提交前崩溃、延迟旧 worker 写入、租约失效和存储故障；检查真实进程终止。

**Completion gate:** CPU 持久化与恢复测试通过。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
