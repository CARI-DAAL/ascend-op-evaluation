# 10: 将现有 Triton 评测作为独立 adapter 运行

**ID:** AOE-10

**What to build:** 用户继续使用现有 definition/workloads 和验证、计时、profiling 意图，但业务逻辑由独立默认 adapter 提供。

**Blocked by:** AOE-08, AOE-09

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 默认 adapter

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

先显式保留 legacy 评测策略及版本；已知比较器缺陷不作为正确行为背书，严格策略由 12 提供。保持 vendored attribution。

## Acceptance criteria

- [ ] 任务输入转换、候选包装、Triton 专属实现规则、默认比较/测量策略、顺序和报告解释属于独立 adapter；可复用生成、执行、比较、测量算法由通用方法承载并接收参数。
- [ ] 默认 adapter 通过 generic execution 使用冻结 Program 和材料，核心不判断 ModelNew、triton.jit 或 check 顺序。
- [ ] adapter 可以在不安装服务包的 worker runtime 中运行；所需可复用库有明确依赖归属。
- [ ] legacy 策略有独立身份；迁移等价仅比较有效支持行为，不把已知错误接受写成永久正确性要求。
- [ ] 常用 verify/benchmark/profile 和 reference-only/candidate-only 场景有客户端到执行记录的测试。
- [ ] 保留 reference/编译缓存及判定复用所需的完整作用域和原始来源，不能把业务缓存变成通用服务判断。

## Validation

CPU fake-device 测试验证封装和调用契约；独立包安装测试证明没有服务实现依赖；交付 NPU 回归入口给 22。

**Completion gate:** adapter 包与 CPU 协议回归通过；设备结果由 22 验收。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
