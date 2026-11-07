# 04: 发现并严格匹配可执行环境

**ID:** AOE-04

**What to build:** adapter 可以查询环境能力并请求固定 runtime；环境不符时得到明确拒绝，而不是在错误环境中运行。

**Blocked by:** AOE-02

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** Runtime 与部署

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

部署管理 runtime；候选只能请求已授权环境。环境注册不携带 benchmark 业务。

## Acceptance criteria

- [ ] 提供有鉴权的 runtime/capabilities 查询，区分能力支持和当前容量，并只公布已实现的执行与隔离特性。
- [ ] 不可变 runtime 描述绑定运行产物、CPU 架构、外部工具链挂载与驱动要求；host 和容器路径有清晰的身份校验。
- [ ] 受理时解析并冻结 runtime 身份，启动前校验实际环境；未知或漂移信息不当作已匹配。
- [ ] 不支持的能力立即拒绝；支持但暂忙可在配额内排队，runtime 别名改变不影响已受理任务。
- [ ] 环境、资源及隔离要求参与执行身份；labels 不参与授权、调度或兼容性证明。
- [ ] runtime 保留期覆盖已接受任务；依赖的 runtime 被移除时明确失败，不静默选择替代版本。
- [ ] profiler 工具能力区分 msprof application、msprof op/msopprof、深度指标和可选 sanitizer，记录版本、架构与 probe 范围；配置中自报的频率/工具存在不能冒充实际测量或可用性证明。

## Validation

经发现与提交接口覆盖匹配/不匹配、别名变化、漂移、繁忙和未知环境；用实际 CPU runtime 完成一次查询到执行。

**Completion gate:** CPU runtime 全链路通过；设备匹配由单卡与实机验收任务补齐。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
