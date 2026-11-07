# 11: 原生 AscendC 工程经相同执行契约构建和运行

**ID:** AOE-11

**What to build:** 用户提交多文件 AscendC 工程和外部执行程序，获得编译日志、动态库或可执行文件及运行报告。

**Blocked by:** AOE-08, AOE-09

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 原生工程示例

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

先限定一个可复现直调模板和已登记工具链；验证核心的原生执行能力，不承诺任意 ACLNN 工程自动适配。

## Acceptance criteria

- [ ] 示例包含源码、头文件、构建入口和必要的 Python/native binding，所有输入字节固定并参与身份。
- [ ] 构建、安装和加载均在任务私有 runtime/workspace，两个同名扩展并行不会污染彼此或共享服务环境。
- [ ] 编译日志和构建产物经标准 outputs 收集，编译失败保持非零退出和原始诊断，不伪装成 infrastructure success。
- [ ] 示例支持不依赖 ModelNew/run() 的原生入口，服务源码不新增 ascendc backend 枚举。
- [ ] 候选构建不计入 adapter 的 kernel timing；编译器/子进程受任务预算及清理约束。
- [ ] 工具链缺失、目标不符、原生加载失败有明确报告与 CPU 测试；真实 AscendC 执行驱动交给设备门禁。
- [ ] 原生 smoke 明确固定 golden、测试输入和比较规则，以已知正确实现及故意错误实现证明报告的判定含义；编译成功或 exit=0 不能作为正确性通过。完整 CANNBench 方法由 AOE-13/23 提供，性能方法由 AOE-18 提供。

## Validation

真实 CPU 原生构建验证文件、编译错误和动态库隔离；固定 AscendC 模板提供目标 NPU 验证命令和预期产物。

**Completion gate:** 原生工程 CPU 路径及 AscendC 验证驱动交付；实机由 22 验收。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
