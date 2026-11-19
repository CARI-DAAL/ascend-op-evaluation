# 面向 agent 的评测 API 与仓库 skill

好接口应让调用者用有限的上下文完成可验证的决定。这里有三个不同的问题：服务能测什么、调用者能从响应证明什么、本轮优化值得测什么。前两个需要跨客户端一致的契约，最后一个取决于优化目标、时间和设备预算。

| 可核对的来源 | 对本服务的启发 |
| --- | --- |
| MCP Tools 规范用 inputSchema 描述参数，声明 outputSchema 时要求返回符合结构的结果；协议错误和工具执行错误有不同表示。[公开规范](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) | 对 HTTP/JSON API 同样可验证请求和结果。让程序直接区分请求无效、执行失败、结果有效但部分缺测，以及正确性检查发现候选有误。这里借鉴契约语义，不需要引入新的传输层。 |
| Google AIP-151 通过长操作资源返回结果，metadata 可承载进度或部分失败，区分提交失败与接受后的执行失败；AIP-155 要求请求标识提供幂等保障。[AIP-151](https://google.aip.dev/151) · [AIP-155](https://google.aip.dev/155) | 沿用 evaluation handle、已有进度读取和幂等键。请求响应丢失时，agent 可以找回同一次采集。部分 case 有证据而整次超时应可同时表达，且进度属于具体 attempt。[提交与恢复](../guides/evaluations.md) |
| Anthropic 的工程文章建议用少量清晰的任务级工具、按需详情和有界结果减少无关上下文，以真实任务评测工具使用质量。它提供实践指导，协议要求以相应公开规范为准。[工程文章](https://www.anthropic.com/engineering/writing-tools-for-agents) | CLI/skill 可组合请求和轮询，先展示少量足够做决策的观测。截断需要保留分母和覆盖信息。用 agent 的正确决定率、重复采集次数、NPU 秒、token 与首个有效判断耗时共同验收。 |

GitHub 的开源 MCP Server 支持按 toolset 或单个工具控制模型能发现的操作。它保留完整底层能力，允许调用端限制当前上下文中的选择。eval 可沿用任务级 CLI 入口，仅在 profile 模式展开采集选项，通过已有 version 接口发现新能力。[GitHub MCP Server](https://github.com/github/github-mcp-server#tool-configuration)

## 如何划界

- **API 和采集器**承诺请求的对象、实际启用的过滤条件和采集上限、观测到的目标记录数、覆盖未知或缺失的原因、计量单位和比较条件。对已存在的规则推导，若要公开可复核的结果，应绑定规则来源、输入证据和适用范围。特定工具命令与 CSV 列映射归 adapter。评测结果已有 coverage、部分状态和定向指标机制可沿用。[证据边界](../explanation/measurement-evidence.md)
- **仓库 skill**说明什么情况下值得采、如何从快到慢补测、什么证据支持哪些假设、下一轮如何复测收益。短示例和选择策略允许独立修订。当前 skill 已提供按目标选命令、保存 handle、消费 partial 警告等入口，可在同一处补充策略。[评测 skill](../../plugins/ascend-op-eval/skills/ascend-op-eval/SKILL.md)
- **端到端验收**可让一个 case 实际运行 A 和 B，采集上限设为 1。直接通过 HTTP 的消费者应能判断 A 只占已观察样本的 100%，而整个 case 的占比未知。再让 agent 在固定预算下决定补采还是停止。前者检验 API 表达事实的正确性，后者检验 skill 是否让决策更好，分别与现有实现做对照。

本次实现沿用 profile 请求和已有的 case 状态。op 的 launch_limit 控制采集，capture_scope 描述实际传给工具的参数和导出记录数；max_kernels_per_case 控制呈现。deep 在分类旁给出 bound_rule，供调用方结合 ratios 复核。旧结果可以省略新增字段。设备开销和 agent 决策质量需要分别用真实运行评估。
