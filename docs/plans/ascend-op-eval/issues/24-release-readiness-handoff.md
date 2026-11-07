# 24: 完成集成审查与可恢复的发布交付

**ID:** AOE-24

**What to build:** 交付一个经审查的集成分支、完整实现/设备证据、兼容矩阵和升级回退步骤，供用户决定部署。

**Blocked by:** AOE-21, AOE-22, AOE-23

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 最终集成

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

开发与验证交付，不自动生产部署、推送、发布或删除旧数据。

## Acceptance criteria

- [ ] 对最终集成差异完成 Standards 与 Spec 两轴 code-review，修复所有实质问题并重跑受影响门禁。
- [ ] 逐项核对设计场景、所有 ticket 验收与实际 capabilities；未实现/未验证能力不能出现在正式能力声明。
- [ ] 在隔离状态副本中演练排空、旧 owner 读取、同幂等键恢复、兼容升级和不兼容回退拒绝。
- [ ] 发布清单固定服务/runtime/adapter 及数据身份，记录可兼容契约与保留期；回退不会丢弃新受理任务。
- [ ] 每张 ticket 有实现 commit、实际测试命令/结果、证据位置和限制；review 后的新改动使相关证据重新验证。
- [ ] 交付集成分支和部署 runbook，保留必要旧读取路径及未迁移数据；生产动作留待用户明确执行指令。

## Validation

独立 review + 最终集成回归 + 隔离升级/回退演练，检查所有证据属于最终代码或有明确未受影响依据。

**Completion gate:** 全部前置门禁满足且最终审查通过；不能因代码齐全就忽略硬件阻塞。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
