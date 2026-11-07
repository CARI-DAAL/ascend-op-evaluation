# 07: 流式读取执行进度并区分报告与执行事实

**ID:** AOE-07

**What to build:** agent 在长任务运行中读取有界日志和进度，并能区分服务观察、程序声明、缺失报告与失败收集。

**Blocked by:** AOE-03, AOE-05

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 观察与结果

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

通用事件和输出清单；不加入 correctness/performance 等固定业务结果字段。

## Acceptance criteria

- [ ] 日志和事件提供稳定 cursor、attempt 标识和截断/过期说明；重连不会把不同 attempt 当成同一次输出。
- [ ] 服务产生的退出、时间、资源和身份事实与 Program 声明的阶段/报告明确标注来源。
- [ ] output collection 的 complete/incomplete/failed 与 execution 状态独立，正常结束缺必需报告可被可靠识别。
- [ ] 报告格式不受固定 JSON schema 限制；服务保留内容和摘要，不把 correct=true 当服务认证。
- [ ] 日志/产物查询遵守 caller 可见性，部分结果不会赋予跨任务读取权限。
- [ ] client disconnect、慢消费者与连续大日志不影响任务租约，并有可验证内存上限。

## Validation

通过 HTTP 执行持续输出与分阶段报告程序，覆盖 cursor 重连、事件来源、日志截断、报告缺失和存储写失败。

**Completion gate:** CPU 事件与证据链测试通过。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
