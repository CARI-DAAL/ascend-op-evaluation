# 02: 提交并恢复一个 CPU 程序的完整执行

**ID:** AOE-02

**What to build:** 调用方上传简单程序与输入，提交 execution，断开连接后仍可按原 handle 取得退出信息和输出。

**Blocked by:** AOE-01

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 执行契约与持久化

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

第一条纵向闭环：新契约、准入、持久队列、worker、产物和查询。先支持小型普通文件及一个部署登记的 CPU runtime；复杂文件树与 runtime 发现分别由后续任务扩展。

## Acceptance criteria

- [ ] 定义独立版本的 ExecutionSpec/ExecutionRecord，包含 Program、Inputs、Runtime、Resources、Limits、Outputs；不复用旧 EvaluationRequest 的业务字段。
- [ ] 调用方通过鉴权接口封存小型程序/输入文件，提交后只在持久 admission 成功的 leased attempt 内执行。
- [ ] 同 caller、同幂等键、同语义请求返回原 execution；不同语义冲突，重放不再次执行程序。
- [ ] Python 程序和原生可执行入口都能经 argv 启动；服务不把数据当 Python 导入或要求 run()/Tensor。
- [ ] 正常 exit=0、exit=1、非服务操作导致的 signal 均记录执行事实；completed 不表示正确，退出和产物收集状态分开。
- [ ] 真实 CPU 子进程经 HTTP→存储→worker→查询闭环演示；旧 v2.1 路由及历史读取保持兼容。
- [ ] 新契约支持明确的方法身份与 parameters，由同一执行生命周期落实；首个 CPU 方法验证参数生效和未知字段拒绝，为六项通用能力建立入口，而不是把任意 JSON 保存后忽略。

## Validation

使用隔离持久存储和真实 CPU 进程验证请求重放、断连恢复、程序非零退出与返回产物；冻结公开契约的示例和测试。

**Completion gate:** 完整 CPU tracer 可运行；扩展任务从此实际契约出发。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
