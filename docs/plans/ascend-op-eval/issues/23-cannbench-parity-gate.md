# 23: 验收外部 CANNBench profile 与固定上游的一致性

**ID:** AOE-23

**What to build:** agent 可以知道 cannbench-a3-2.0 profile 对齐了哪个具体上游快照，以及正确性、失败和性能结果的验证范围。

**Blocked by:** AOE-13, AOE-22

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** CANNBench 兼容验收

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

兼容性归外部 adapter；公开快照对齐与网站完整对齐分别声明，未知信息不能靠别名补齐。

## Acceptance criteria

- [ ] 核实 A3-2.0 名称对应的数据、上游 harness、runtime 与规则；不可取得的精确网站配置/隐藏数据列为未覆盖。
- [ ] 相同候选、固定任务、输入分布/seed、golden、精度策略、测量参数、基线与评分用于直接上游和服务路径。
- [ ] 覆盖正确实现、错误输出、编译失败、运行错误、部分 case、缺结果和多 kernel 等有代表性的差分样例。
- [ ] 判定、覆盖、失败分类和评分按固定快照语义一致，性能落在事先固定的统计判据内。
- [ ] 原始两侧报告、构建产物摘要和实际设备来源归档，adapter 解析不得丢失影响结论的字段。
- [ ] profile 仅在实际验证范围内标 verified；无法证明网站完全一致时不得发布无范围的完全对齐声明。
- [ ] 差分记录上游实际 golden/checker/perf strategy、输入池/输出复检、warmup/repeat/batch 设置和聚合公式；包括 sum-of-medians 与 median-of-sums 不相等的样例，禁止使用另一套 skills/msprof 协议冒充一致。

## Validation

运行固定快照的差分驱动，产出逐场景对比与统计报告；环境缺失时保留 adapter 实现完成状态但本验收 ticket 阻塞。

**Completion gate:** 对指定公开快照的兼容验收完成；网站完整对齐只在取得并验证所需证据后成立。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
