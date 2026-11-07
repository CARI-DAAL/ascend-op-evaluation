# 14: CPU 构建产物可传给独立 NPU 执行

**ID:** AOE-14

**What to build:** 外部 adapter 可先在 CPU runtime 构建，再把封存产物交给另一 NPU execution，无需占卡等待编译。

**Blocked by:** AOE-11

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 外部编排与产物

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

两个普通 execution 和 artifact handle 的组合；核心不增加 build 阶段状态机、DAG 或业务编译缓存。

## Acceptance criteria

- [ ] CPU 构建和 NPU 运行有独立 handle/attempt，通过有访问权的封存 artifact 传递产物。
- [ ] 外部构建清单绑定全部源码、编译参数、工具链、目标 SoC/ABI 和产物摘要，运行前按 adapter 契约检查。
- [ ] 错误目标、损坏产物、过期引用、无权限和不匹配 runtime 明确拒绝，不自动重新解释产物。
- [ ] 外部 adapter 在中断后恢复已接受阶段，复用同一成功构建；不同运行执行仍产生新测量证据。
- [ ] 共享的编译产物只读，安装/加载工作区私有；没有共享可变构建目录或自动正确性/时延复用。
- [ ] 同机本地路径与服务产物传输的选择不改变摘要、权限或可恢复性。

## Validation

真实 CPU 编译→第二 CPU 进程加载验证完整手递流程；NPU variant 交给 22；对目标/摘要错误做拒绝测试。

**Completion gate:** 跨 execution 产物流程 CPU 验收通过。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
