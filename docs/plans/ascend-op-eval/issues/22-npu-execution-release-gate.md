# 22: 目标 NPU 验收执行、隔离、多卡与计时

**ID:** AOE-22

**What to build:** 在目标 Ascend 环境证明单卡、原生构建、隔离子执行、多卡和 profiler 的实际能力，明确发布可支持范围。

**Blocked by:** AOE-21

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 硬件验收

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

使用隔离测试实例和确认可用的卡；不占用生产任务的设备。缺硬件只记录阻塞，不以 mock 替代。

## Acceptance criteria

- [ ] 记录精确服务/runtime/program/输入摘要、硬件与驱动、CPU 架构、卡映射及测试环境状态。
- [ ] Python/Triton/AscendC 原生程序在真实单卡运行，正确、错误、编译失败、加载失败和运行失败均可恢复证据。
- [ ] 取消、超时、子进程/设备上下文清理、worker 故障恢复及后续已知正常任务实际通过。
- [ ] controller/candidate 隔离和大数据/状态交换在设备上验证；只声明已验证的隔离强度。
- [ ] 同机多卡 rank 运行、通信及一 rank 失败后的整组清理通过；缺多卡环境则该能力维持未验收。
- [ ] 对照直接运行与服务执行的时延/trace，先采集噪声并固定阈值，再做重复样本验收；原始记录可追溯。
- [ ] 验证异步直调、自有 stream、同名 kernel 多次 launch、profiler 导出完成、空导出和指标缺失；逐一记录已验证的 msprof application/op/deep 模式及未支持范围，诊断采集不参与正式 latency。

## Validation

执行前确认设备租约与隔离测试环境，运行已交付的门禁驱动并归档原始结果；依据预定阈值判定，不事后调参求通过。

**Completion gate:** 所声明设备能力均有实机证据；缺少任一必要环境时标 blocked，不标 done。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
