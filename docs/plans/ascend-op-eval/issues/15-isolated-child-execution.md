# 15: 评测 controller 可启动受控隔离子执行

**ID:** AOE-15

**What to build:** 外部裁判能在同一 attempt 中启动隔离候选，等待或取消并封存输出，而不把服务管理权限交给候选。

**Blocked by:** AOE-03, AOE-04, AOE-05, AOE-06

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** Runtime 子执行

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

提供通用 exec/wait/cancel/seal_outputs 能力；先以 CPU controller/candidate 完成纵向闭环。

## Acceptance criteria

- [ ] controller 通过 attempt 范围的受限接口创建子执行，子进程只获得明确指定的输入、工作区和已授权资源子集。
- [ ] candidate 无法访问 controller 执行凭证、golden 私有目录和最终报告目录；不同 sandbox/身份的机制有实际测试。
- [ ] 子执行不能增加父预算、请求未预留设备或任意挂载宿主目录；父子总资源使用受同一上限约束。
- [ ] 父 Program 退出、取消或丢失租约时所有子执行清理完成才能结束 attempt/释放资源。
- [ ] 子输出停止写入或取得一致快照后封存，延迟写入和路径替换不能改变已发布内容。
- [ ] 同一接口支持普通原生子程序，服务不理解 reference/candidate 的业务含义；整体 harness 模式仍可使用。

## Validation

通过外部 CPU controller→generic execution→隔离子进程的公开路径，测试越权、预算、父退出、租约失效和输出封存竞态。

**Completion gate:** CPU 子执行与隔离机制通过；设备能力由 16/22 验收。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
