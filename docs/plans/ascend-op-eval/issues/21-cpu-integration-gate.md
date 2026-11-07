# 21: 完整 CPU 集成与故障恢复验收

**ID:** AOE-21

**What to build:** 所有实现汇入后，通用核心和外部 adapters 在公开接口上通过统一故障与兼容验收，形成可供设备验证的构建。

**Blocked by:** AOE-07, AOE-14, AOE-16, AOE-17, AOE-18, AOE-20

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 集成验收

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

验收最终集成代码，不以各分支单测报告替代集成结果；设备结论留给独立任务。

## Acceptance criteria

- [ ] 运行适用的完整 CPU、lint、安装和契约检查，并记录精确集成 revision、依赖、命令、通过/跳过/失败数量。
- [ ] 公开路径覆盖 Python/native、两种不同报告、目录输入、非零退出、缺报告、日志截断和收集故障。
- [ ] 覆盖取消/完成竞态、worker 丢失、旧 attempt 写入、产物 GC、环境漂移、独占资源和组分配失败。
- [ ] 隔离 controller/candidate、越权 artifact、路径逃逸和共享构建污染的反例不能通过。
- [ ] 执行内核与服务依赖不包含 benchmark adapter、评分或专属默认规则；通用比较/测量方法接受参数，两个独立 adapter 调用同一契约，变更精度与采样参数确实生效。
- [ ] 生成版本化设备验收清单及测试构建身份，未运行硬件项明确保持未验收。

## Validation

按仓库实际工具配置运行全量 CPU 门禁及干净安装/恢复演练；提交可复查的原始测试证据。

**Completion gate:** 完整 CPU 集成通过；不可将后续设备 tickets 自动标完成。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
