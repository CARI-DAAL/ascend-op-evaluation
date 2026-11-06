# 通用评测能力契约

本文是目标设计，不是现有服务接口。实现 adapter 前核实实际能力。

## 职责

| 层 | 负责 |
| --- | --- |
| 执行内核 | immutable inputs、环境、设备租约、进程、期限、取消、恢复、产物与来源 |
| 服务通用方法 | build/invoke、输入/参考执行、结构校验、数值比较、测量、profiling；校验方法参数 |
| 外部 adapter | 任务解析、默认值/overrides、方法选择、参数映射、profile、基线/评分与任务结果 |

通用方法层让 adapter 不必重写基础能力；执行内核不认识 benchmark。服务不能把某组默认值写死为榜单规则。

## 方法接口

MethodCall 包含不可变 `method_ref`、`parameters`、命名 input artifact 引用。MethodDescriptor 包含：

- 实现/依赖摘要、入口、参数 schema 与版本。
- 默认值、类型/范围/组合约束、单位和规范化规则。
- 必需 runtime/tool/device/权限能力，输出 schema 与原始产物类型。
- 指标含义、错误类别、是否重复执行/重放候选。

实现可以由部署提供，也可使用独立发布且满足运行政策的方法包。方法在 worker 执行，不等于把 benchmark adapter 导入服务源码。

高层 EvaluationPlan 组合 MethodCall，由同一执行内核履行。完整上游 harness 可作为一个方法包运行，保留难拆分语义；同样需要参数 schema、能力要求、消费位置与证据，不能靠不透明 blob 掩盖缺口。

说明性结构，不是当前可调用请求：

```json
{
  "correctness": {"method_ref": "sha256:CHECKER_DESCRIPTOR", "parameters": {"atol": 0.00001, "rtol": 0.001}},
  "measurement": {"method_ref": "sha256:MEASUREMENT_DESCRIPTOR", "parameters": {"warmup": 3, "repeat": 5}}
}
```

数字只展示参数位置。方法 schema 决定允许的字段；allclose 方法不能吞掉 MERE 或特殊回退字段。

## 参数、身份与失败

adapter 按上游优先级合并任务、profile 与用户 overrides；服务校验 schema/资源，补全默认值后保存 requested/effective 配置及摘要。零、false、null 与未提供分别处理。

service contract、method implementation/schema、adapter、upstream framework、task data、baseline、runtime 分别版本化。alias 只用于解析；语义参数参与执行身份和相关缓存键，显示标签不是配置来源。

未知方法/字段、非法组合、缺能力明确失败。不能静默改精度、换 collector、降 profiler level、缩短 repeat 或扩大资源。

## 资源映射

服务预留设备后映射到隔离域；adapter 表达型号/数量/拓扑与程序内逻辑设备，不能要求任意宿主设备路径。方法内 timeout/retry/batch 均受父 deadline/预算约束。

多轮 profiler 或多 rank 必须声明完整需求和逐次执行身份。任务内并发与跨任务独占是不同约束；不能将 processes-per-card 直接拆成竞争同卡的独立请求。

## 结果

执行记录回答运行字节、环境、参数和退出事实；方法报告回答按哪个算法得到何种观测；adapter 解释任务 verdict/profile 兼容性与 score。摘要和 attempt 连接三者，但不能混淆权威。

strict profile 固定规则，仅允许预先声明不改变协议的覆盖；其他有效覆盖进入 custom 模式。profile 名称不能自证榜单兼容，性能差分采用预先确定的统计范围。
