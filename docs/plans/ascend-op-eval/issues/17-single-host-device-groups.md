# 17: 原子预留同机多卡并运行多 rank 程序

**ID:** AOE-17

**What to build:** 通信算子和多 rank 程序可以申请完整设备组，只有全部资源到位后启动，失败后整组清理。

**Blocked by:** AOE-06, AOE-08

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 设备调度

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

仅同机多卡；跨机保留明确 unsupported 响应，不用多个独立单卡 execution 冒充 collective。

## Acceptance criteria

- [ ] 资源请求表达数量、型号及已支持拓扑；设备组原子预留，不因部分占卡形成死锁或重复分配。
- [ ] 一个 attempt 拥有整组设备，记录全部物理身份、逻辑映射和 rank 可见性。
- [ ] Program 自行选择 launcher 和通信协议；runtime 提供声明的组内 IPC/网络能力，核心没有 collective 算子分支。
- [ ] 单 rank 失败、取消、lease 丢失或卡异常触发整组清理；未清理完成的设备保持不可用。
- [ ] 队列区分暂时无法满足与永远不支持；与单卡任务竞争时具有可测试的公平/饥饿限制。
- [ ] CPU 仿真覆盖原子分配、失败和恢复，真实多卡驱动包括通信正确性及故障清理。
- [ ] 多 rank profiler 及导出子进程属于原设备组租约，记录各 rank/device 产物；adapter 按工具已验证范围选择模式，不对未支持的 fork 多 rank 场景无声使用 msprof op，跨 rank 聚合方法单独标识。

## Validation

故障注入的设备组调度测试和公开请求集成；真实多卡测试由 22 执行。

**Completion gate:** 多卡机制 CPU 验收和可运行设备门禁交付。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
