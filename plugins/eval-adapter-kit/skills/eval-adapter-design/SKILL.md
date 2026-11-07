---
name: eval-adapter-design
description: 为算子评测任务设计或审查外部 adapter，建立参数到通用评测能力的完整映射、版本化方法配置与一致性验收。用于新 benchmark 接入、CANNBench 等上游对齐、adapter 规范和参数覆盖审查；普通提交已有评测任务无需使用。
---

# 外部评测 adapter 设计

围绕六项能力设计 adapter：准备数据、构建加载、执行、比较、测量、诊断。任务格式、benchmark profile、基线与评分留在外部 adapter；服务复用通用能力。交付一份简洁规范与参数对应表，不为单个 benchmark 再造配置框架。

## 先确认实际接口

读取目标服务的当前契约、capabilities 和相关实现，再读该任务的固定版本源码。区分已实现能力、设计提案和未知项。本插件给出设计规范，不声明目标服务已实现示例接口，也不提供 CANNBench adapter 的可执行实现。

只处理用户请求的设计、审查或实现范围。需要服务实现时，新增的是可复用能力；不能通过在核心加入 benchmark 名称分支来完成接入。

## 工作流程

1. **固定对象。** 记录 upstream revision、任务数据/规则版本、入口与适用硬件。阅读 [通用能力契约](references/capability-contract.md)，确定执行内核、通用方法、外部 adapter 的职责。
2. **列出参数面。** 枚举 CLI、配置对象、任务 schema、环境变量、hooks/插件、数据/基线与调度选项；追踪默认值合并和实际消费位置。只读 argparse 或文档不能证明完整。建立带来源的 inventory，明确尚未覆盖的动态入口。
3. **逐项映射。** 标出 adapter 输入、目标方法参数/产物/资源/预算、类型与单位、有效默认值、条件、转换和能力要求。读取 [参数覆盖规则](references/parameter-coverage.md)。区分“可表达”“已实现”“实机验证”；未知项保留 gap。
4. **选方法。** 比较、采集、归属、聚合使用固定方法身份与参数 schema。公共方法由服务复用，特殊算法以独立方法包提供。方法版本和参数共同绑定报告；同名工具或相同 repeat 不代表同一语义。
5. **写交付。** 按 [adapter 规范模板](assets/adapter-spec.template.md) 生成设计，参考 [能力组合示例](assets/evaluation-plan.example.json)。尊重目标项目文档位置，具体化占位值或列为未决项。
6. **验收设计。** 使用 [一致性验收指导](references/conformance.md) 定义参数变化、交互、错误路径及直接上游差分测试。对应表用于查漏，真正的生效与等价需要测试证据。

## 按需参考

- 接入 CANNBench 时读 [固定快照参考](references/cannbench-reference.md)；它展示映射思路，不是可运行 adapter 或已认证的完整线上参数集。
- 使用 profiler 时分别定义正式计时、诊断与 instrumentation 身份。kernel 序列、stream、conditioning、aggregation、rank 聚合及输出有效性属于协议，不能只传 warmup/repeat。

## 完成条件

交付规范明确独立部署、服务能力要求、参数实际去向、版本与证据身份、兼容/自定义模式、失败解释和验收方案。汇报覆盖范围、缺口和实测程度。

“所有参数都支持”需要固定范围的参数清单、每项生效证据及交互验收。任意 JSON 字段或 CLI passthrough 不足以证明；资源不足、方法未知或工具不兼容要明确返回。
