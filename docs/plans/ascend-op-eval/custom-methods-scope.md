# 自定义评测方法实施范围

Historical implementation record. Current interface and qualification are documented in the guides and support matrix; this record retains its original acceptance scope.

基线：a34ed5923aa02ab82ac34480c0a4c4a25166163f；本地集成分支 feat/custom-methods。
来源：用户指定的 custom-methods-implementation-prompt.md。本记录保留实施与验收范围，不替代该原始指令。

## 必须实现

- 方法包封存、不可变摘要和调用方所有权；元数据解析不导入用户代码。
- 版本化 descriptor、参数 schema/defaults/约束、输入/输出协议、依赖及 runtime 要求。
- requested/effective 参数、方法/依赖/输入/环境身份冻结；别名更新不改变已准入任务。
- 自定义 checker 和 measurement 在 worker 子进程中实际执行；checker false、异常、超时、协议错误与环境不足分别报告。
- checker 独立于 candidate.forward；用户方法报告明确为 caller_method 权威，不冒充服务认证。
- 日志及原始产物有界、可恢复且绑定 attempt；不复用旧判定或时延缓存。
- 复用现有 admission/store/worker/租约/期限/恢复，补充取消，不建立第二任务状态机。
- 新契约 custom-method-v1 显式标识；旧 native/Triton 默认路径、历史记录继续工作。
- 可运行客户端、checker/measurement 示例与服务外的固定 CANNBench 接入；服务核心无 CANNBench import/名称分支。
- 公开接口验证参数变化、不同聚合、多 kernel/重复 launch、错解/异常、取消/恢复/过期 attempt。

## 实施分工和依赖

| 任务 | 负责人 | 交付 | 前置 |
| --- | --- | --- | --- |
| CM-01 | custom_registry | 包/产物 registry、契约、HTTP、参数校验、准入/取消及恢复 | 无 |
| CM-02 | custom_runtime | 真正方法子进程、能力检查、结果/产物、worker 集成 | CM-01 契约；可先按约定开发 |
| CM-03 | custom_client | 独立 CLI、外部示例、固定上游差分及覆盖矩阵 | CM-01 契约；实际验收依赖 CM-02 |
| CM-04 | root | 集成、公开接口闭环、全量回归、独立复审及交付报告 | CM-01/02/03 |

使用独立工作树，集成串行进行。分支测试不能替代最终集成测试。

## 验收界限

本机无 NPU、CANN、msprof。完成可执行开发和 CPU 差分，不以 mock、skip 或 exit=0 代替真实设备或线上兼容结论。报告分别回答自定义方法是否端到端可用、固定公开 CANNBench 哪些行为已验证、哪些仍需 server 验收或未支持。

本轮不推送、发布、生产切流或删除历史数据。既有未提交设计材料保留。

## 实施结果

CM-01、CM-02、CM-03 已集成；CM-04 的 CPU 集成和独立复审完成。
全量回归 2693 通过、20 项环境相关跳过、0 失败；新增自定义方法测试无跳过。
审查发现的动态参数默认值、原子改名产物扫描、首次导入循环及 OpenAPI
类型问题均已修复并经独立复查。临时实施工作树已清理，提交分支保留。

接口与调用见 `docs/guides/custom-methods.md`，固定上游覆盖矩阵见
`adapters/cannbench/src/ascend_op_eval_adapter_cannbench/bundle/README.md`。准确的代码版本、命令、
测试日志摘要及服务器验收计划记录在 `custom-methods-validation.json`。
完整 NPU harness 尚未通过设备验收，不声称完整 CANNBench 快照覆盖。
