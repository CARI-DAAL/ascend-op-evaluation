# 09: 外部 adapter 按固定 profile 提交和恢复执行

**ID:** AOE-09

**What to build:** 独立于服务安装的 adapter 客户端可以将 profile 解析成执行请求，上传材料、提交、恢复并读取报告。

**Blocked by:** AOE-03, AOE-04, AOE-06, AOE-07

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 外部 adapter

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

提供协议客户端与 adapter 开发约定，不建立服务端 benchmark registry。开发落点为同仓独立发行包，服务不导入或依赖它。

## Acceptance criteria

- [ ] 客户端独立安装，不需要服务端 Python 包或 Torch；服务也不依赖 adapter 包。
- [ ] 外部 profile alias 在提交前解析为固定 program、任务配置、runtime 和材料摘要，解析结果作为可追溯输入保存。
- [ ] 服务不解释 profile 名称；改变评分、seed 或 timing 参数必须改变实际配置摘要。
- [ ] 提交超时或断连后使用原 owner handle 和幂等键恢复；不向另一实例盲目重提。
- [ ] 客户端分别呈现执行、终止与产物状态，缺报告不会被包装成通过。
- [ ] 提供最小自定义 adapter 示例，演示同一服务运行两个不同报告格式的程序而无需改核心。
- [ ] adapter 可查询并组合准备数据、构建加载、执行、比较、测量、诊断的方法；方法版本、参数 schema、有效值与能力缺口可见。任务转换/profile/评分留在外部，不要求每个 adapter 重写公共比较与采集实现。

## Validation

独立虚拟环境安装客户端，使用真实 CPU execution 接口验证 profile、上传、重连、错误和报告解析。

**Completion gate:** 外部客户端与两种 CPU 示例通过。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
