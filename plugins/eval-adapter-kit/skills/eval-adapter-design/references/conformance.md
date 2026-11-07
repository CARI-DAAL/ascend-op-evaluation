# Adapter 一致性验收

执行完成、方法输出有效、任务判定通过分别报告；exit=0、JSON 可解析、覆盖检查通过不替代后两者。

## 参数生效

每项定义可观察行为：展示字段检查报告；精度字段构造阈值边界正反例；采样字段检查真实样本/launch 数量；资源/路径字段检查映射和拒绝。保存 requested/effective 配置、方法摘要、调用/数据证据及预期/实际结果，未知字段拒绝。

## 上游差分

相同冻结材料直接运行上游与经过 adapter/service 运行，比较输入/参数、golden/输出契约、失败分类、覆盖、原始采集归属、聚合和评分。

覆盖正确实现、故意错解、编译/加载/运行失败、超时、缺报告、非法组合、特殊值、重复同名 kernel、多 stream 和实际涉及的多 rank。CPU 与设备证据分开记录。

统计阈值在采样前确定。median(sum)、sum(median)、mean、跨 rank max 不互换；collector、conditioning、同步、batch 或工具版本变化后重新限定可比范围。

## 工具边界

- Event 覆盖真实 stream；末尾全设备同步不能修复 end Event 早于目标工作。
- profiler 完成后验证导出和 launch 序列，保留原始产物；空导出不是零时延。
- op/deep 多轮结果分别标来源；缺指标不是零，诊断时延不合并为 benchmark latency。
- sanitizer 不代替数值正确性，插桩时间不代表正常性能。
- 固定公开快照与线上榜单完整配置/隐藏用例的兼容性分别声明。

每份 evidence 记录 upstream/data/runtime/method/adapter 身份、有效配置、实际设备工具、原始产物、命令和验证范围。能力不足留下具体 gap，保留已完成工作。
