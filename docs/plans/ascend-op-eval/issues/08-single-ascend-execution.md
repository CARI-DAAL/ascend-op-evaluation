# 08: 在独占 Ascend 卡上运行任意评测程序

**ID:** AOE-08

**What to build:** 同一 execution 契约可以运行 CPU 或单卡 Ascend 程序，并准确记录真实设备和逻辑设备映射。

**Blocked by:** AOE-04, AOE-05

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 设备运行

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

泛化设备分配，不加入候选语言或 benchmark 分支；实机功能验收集中在设备门禁。

## Acceptance criteria

- [ ] 显式设备请求决定 CPU/单卡执行，runtime 能力与资源健康共同决定可调度性。
- [ ] 同一物理卡不同时授予两个独占任务；每个 attempt 记录实际设备身份及隔离域内映射。
- [ ] CPU 任务没有 NPU 访问；指定卡之外的设备不暴露给普通 execution。
- [ ] 健康探针和恢复由部署控制，与候选 Triton/AscendC 类型无关；异常结束后的卡状态影响后续调度。
- [ ] 不支持型号明确拒绝，暂忙排队，清理未确认的设备不复用。
- [ ] 提供经公开接口运行的真实 NPU smoke 驱动和证据格式；CPU 测试覆盖分配、映射、拒绝、租约与清理状态机。

## Validation

先用可替换设备模块测试公开执行接口及调度，再交付无需修改核心的实机 smoke；本 ticket 的完成证据注明尚待设备门禁。

**Completion gate:** 设备机制 CPU 验收与 NPU 驱动交付；真实单卡能力由 22 验收。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
