# 16: 同一设备租约内隔离 reference 与候选状态

**ID:** AOE-16

**What to build:** adapter 可保持裁判和 golden 私有，在同一预留设备上依次运行独立状态的 reference/candidate，并判断输出与副作用。

**Blocked by:** AOE-08, AOE-12, AOE-15

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 设备子执行与默认 adapter

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

组合设备执行与通用子执行能力；数据布局/alias/输出解释在 adapter 中，核心不新增 Tensor 协议。

## Acceptance criteria

- [ ] controller 能把已预留卡的允许子集授予子执行；实际物理/逻辑映射与父租约一致。
- [ ] 独占测量子执行不会与另一子执行意外重叠；取消和异常清理覆盖父子所有设备上下文。
- [ ] adapter 的数据交换保留非连续布局、内部 alias 和声明的 inplace 后状态，reference 与 candidate 不共享可写状态。
- [ ] candidate 无法修改 controller 报告或读取不应可见的 golden；报告区由 controller 与宿主收集器掌握。
- [ ] 大数据通过本地 artifact/映射文件等已实现方式交换，不要求经客户端往返；未经实现的设备 IPC 能力明确拒绝。
- [ ] 记录实际隔离强度和剩余设备/驱动边界，不把进程隔离等同于完整硬件对抗隔离。

## Validation

CPU 可运行的状态/隔离回归经真实子执行验证，设备映射用替身覆盖；交付实际 NPU 状态交换和清理场景给 22。

**Completion gate:** CPU 组合回归与设备验证驱动交付；真实设备隔离由 22 记录范围。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
