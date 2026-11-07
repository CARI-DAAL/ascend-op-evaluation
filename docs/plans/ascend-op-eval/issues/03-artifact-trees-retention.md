# 03: 安全传递多文件工程和大产物

**ID:** AOE-03

**What to build:** 调用方上传源码工程或数据集，任务能使用完整文件树；日志、动态库和报告可按摘要下载并在排队与恢复期间保留。

**Blocked by:** AOE-02

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 产物存储

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

通用字节与文件树存取，不解析 Tensor、benchmark 或构建语义。

## Acceptance criteria

- [ ] 支持多文件、二进制、嵌套目录和有大小限制的流式传输；规范文件树摘要包含相对路径、字节及影响执行的文件属性。
- [ ] 封存产物不可原地修改；访问权限与摘要分离，知道其他 caller 的摘要不能读取其材料。
- [ ] admission 对程序和输入建立持久引用；排队、运行与可恢复 attempt 不会因 TTL 或 GC 丢失输入，释放引用的竞态有测试。
- [ ] 归档解包和输出收集拒绝路径逃逸、符号链接及不支持的特殊文件，限制展开大小/条目数；固定快照后计算摘要。
- [ ] 输出不存在、截断、超限、存储失败分别记录，保留已得到的进程退出事实；终态引用只指向已封存产物。
- [ ] 提供保留期、明确的产物过期响应和可重复 GC；失效 attempt 和未完成上传可回收且不删除在用材料。

## Validation

公开上传/执行/下载接口覆盖文件树、二进制、大数据有界内存、越权、恶意归档、收集竞态和保留期；真实 CPU 程序读写材料。

**Completion gate:** CPU 产物与持久引用测试通过。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
