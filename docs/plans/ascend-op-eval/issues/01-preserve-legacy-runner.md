# 01: 提取通用进程执行模块，保持现有评测行为

**ID:** AOE-01

**What to build:** 现有客户端仍可完成提交、验证和结果恢复，同时进程监督与文件收集可以脱离算子检查单独使用。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 运行器

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

仅做必要 prefactor；保持 v2.1 请求、错误归因、结果和存储身份。冻结既有行为不代表认证现有比较器正确。

## Acceptance criteria

- [ ] 用公开评测接口的特征测试覆盖成功、候选错误、超时和失效 attempt，重构前后响应语义一致。
- [ ] 通用进程执行模块接受 argv、工作区、环境、预算和租约；不依赖 Triton、ModelNew 或四种 check 的枚举。
- [ ] 进程监督与路径安全的产物读取可以由非评测程序使用，同时保留既有后代清理行为。
- [ ] 服务启动、worker 装配和既有 fake-engine 测试使用同一通用模块，不复制第二套执行实现。
- [ ] 既有输入适配、精度规则和业务缓存仍留在原路径，后续 ticket 再迁移；保留上游版权和许可证头。

## Validation

先为已有接口建立行为特征测试，再通过重构保持绿色；运行运行器、sandbox、worker 和 HTTP 恢复相关 CPU 测试。

**Completion gate:** CPU 行为回归；不需要据此声称 NPU 数值或性能等价。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
