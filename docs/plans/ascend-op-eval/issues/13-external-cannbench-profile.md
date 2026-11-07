# 13: 外部 CANNBench adapter 运行固定上游快照

**ID:** AOE-13

**What to build:** agent 选择外部 CANNBench profile，即可运行固定上游 harness 并获取原始报告及解析结果。

**Blocked by:** AOE-08, AOE-09

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** CANNBench adapter

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

采用上游真实 Program 与任务包，不用默认 verifier 替代精度或计时逻辑；A3-2.0 的别名只有在证据充分时才标为已验证。

## Acceptance criteria

- [ ] 固定上游 revision、任务/基线材料、配置与 runtime 摘要，记录获取来源；不依赖移动 master 或可变镜像 tag。
- [ ] profile 位于外部 adapter，区分 benchmark 数据版本、adapter 版本、CANN 版本与服务契约；核心没有 CANNBench 分支。
- [ ] 按固定快照的真实构建/加载/执行约定运行，保留原始上游报告和日志，再由 adapter 解析。
- [ ] 编译失败、运行失败、错误结果、部分 case 和缺报告有协议测试，不仅测试 happy path。
- [ ] 公开快照与网站实际环境/隐藏数据的差异明确记录；没有依据时不能为 cannbench-a3-2.0 声称完全对齐。
- [ ] 提供同一提交直接运行上游与经过服务运行的对照驱动，真实设备/统计一致性由 23 独立验收。
- [ ] 方法清单固定有效 golden_precision、oracle/native hooks、checker/阈值/特殊值策略、输入生成与性能输出检查，以及 collector、权威数据源、launch 归属、聚合公式和有效采集参数；原始配置与方法身份随报告保存。
- [ ] 以已审查的 cann-bench 提交 f0488d95b4d44a6a0da1b8cd99e91fbd06181962 为候选基线，核对其 framework=1.0.0 / tasks=2.0.0 与所需 profile 的关系。若选择不同快照则重新核对调用链；规范与代码冲突须记录，不能自行替换默认 CSV strategy 为 Event、旧 dequeue trace 或 skills 的另一种聚合。
- [ ] 按项目 adapter skill 给出固定范围的完整参数对应表，覆盖 CLI/config/env/task/hooks，逐项映射六项能力及资源；服务代码不包含 CANNBench adapter。公共方法不足时使用独立方法包，必须有实际消费与生效测试，不能以任意 JSON/argv 透传替代支持证明。

## Validation

固定样例报告解析、打包/摘要测试和 CPU 可执行部分；检查服务安装不依赖该 adapter，交付 NPU 对照驱动。

**Completion gate:** 固定快照 adapter 可构建且 CPU 协议通过；正式兼容性由 23 验收。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
