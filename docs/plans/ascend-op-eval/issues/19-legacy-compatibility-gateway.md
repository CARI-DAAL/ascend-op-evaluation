# 19: 旧客户端继续提交并恢复历史任务

**ID:** AOE-19

**What to build:** 旧调用方通过独立兼容入口继续工作，历史 evaluation 按原 owner 恢复，新 execution 不被伪装成历史证据。

**Blocked by:** AOE-06, AOE-10, AOE-12

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 兼容迁移

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

expand–contract 的兼容阶段；旧 v2.1 模型与业务翻译留在外部 gateway/adapter，核心最终只持有通用契约。

## Acceptance criteria

- [ ] 兼容入口显式翻译旧提交意图到默认 adapter，旧协议继续选择有明确身份的 legacy 策略，严格策略需显式新入口/版本。
- [ ] 旧 handle、幂等键、owner 和历史 payload 在恢复时保持原含义；不套用当前 runtime 或 adapter 身份补造历史 provenance。
- [ ] 同一请求不能因新旧入口重试产生无意重复执行；转换后无法忠实表达的行为明确拒绝。
- [ ] 历史读取、当前提交、排空期间重放和升级后读取都有兼容矩阵与自动化用例。
- [ ] 新 execution 契约独立版本化，gateway 依赖 adapter 而核心不导入 gateway 的业务模型。
- [ ] 在隔离数据副本上演练切换和回退；不删除现有 Redis namespace/volume，不执行生产切流。

## Validation

以冻结旧请求/响应夹具和隔离 Redis 演练新旧入口、恢复、幂等及排空，比较语义而非伪造字段。

**Completion gate:** CPU 兼容演练通过；真实部署 gate 在 24 汇总。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
