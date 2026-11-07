# 05: 取消和资源预算约束覆盖整个进程树

**ID:** AOE-05

**What to build:** 用户可以取消任务；程序、编译器及脱离 session 的后代在超时或预算耗尽后被清理，资源可安全再次使用。

**Blocked by:** AOE-02, AOE-04

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 运行器

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

实现通用生命周期限制；不把超时自动归因于候选算子。

## Acceptance criteria

- [ ] 总 deadline 从 admission 计时，run timeout 从运行开始计时；排队不能绕过总期限。
- [ ] cancel 幂等，终态不回退，取消与完成竞态只有一个合法结果；断开 HTTP 等待不会取消任务。
- [ ] 进程数、CPU/主存、scratch、输出和日志预算在所声明 runtime 上实际限制；无法强制的能力明确不支持。
- [ ] 进程组、重新创建 session 的后代和编译子进程都随取消、期限或租约失效退出。
- [ ] 记录终止原因、触发预算、已收集输出和清理状态；日志超限不会导致服务内存无限增长。
- [ ] 清理未确认时资源不重新分配；正常完成和异常清理都有真实 CPU 进程测试。

## Validation

通过 HTTP 提交 fork/setsid/持续输出/内存消耗程序，测试期限、取消和后代清理；受限测试环境不支持的限制必须有能力拒绝测试。

**Completion gate:** CPU 运行与清理机制通过；设备残留恢复在实机门禁验收。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
