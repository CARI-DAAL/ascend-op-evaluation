# 18: 外部程序在声明环境中完成计时与 profiler 导出

**ID:** AOE-18

**What to build:** 默认及原生 adapter 可选择自己的计时窗口和 profiler，得到原始 trace、测量定义与可追溯结果。

**Blocked by:** AOE-10, AOE-11

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 测量与工具

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

工具能力归 runtime；采集与解析实现可作为服务通用方法复用，外部 adapter 选择方法、参数和任务策略。固定 CANNBench 快照保持其语义。

## Acceptance criteria

- [ ] capabilities 只声明实测/实现的 profiler 权限与工具版本；请求不支持的能力明确拒绝。
- [ ] wall time、Event latency、kernel-sum 和端到端延迟明确区分；服务不自动转换或制造 speedup。
- [ ] 默认 adapter 对重复同名 kernel 按实际调用/采集窗口统计，不以名称假设每次只 launch 一次。
- [ ] warmup、repeat、stream 同步、cache 清理和测量顺序由冻结 Program/config 决定，构建时间不会混入 kernel timing。
- [ ] profiler 原始数据、日志、解析结果和未测/部分测量状态都经标准 artifacts 返回。
- [ ] 提供直接执行与服务执行的对照采样、预热和波动阈值配置；实际性能等价在 22 冻结阈值后验收。
- [ ] 分别交付有方法身份的 benchmark、msprof application 和 op/deep 诊断 recipe；工具不支持时明确拒绝。CANNBench 默认 CSV 的 sum-of-per-kernel-medians 与 skills application 的 median-of-sequence-sums 不互换。
- [ ] msprof application 通过固定 runner/launch manifest 核对 preparation、warmup、target 的数量、顺序和归属，统计目标完整序列；导出为空、缺 launch、重复或乱序都产生明确无效证据，不依赖退出码判断。
- [ ] Event 方法验证 AscendC 的真实 launch stream 与事件依赖；异步 profiler 调用在推进 step 前正确同步。全设备 synchronize 发生在 end Event 之后不能替代缺失的跨流依赖。
- [ ] op/deep 的各 metric pass 和 sample-based 结果保留各自执行身份、原始 CSV/数据库及缺失指标；诊断时延、插桩时延和未支持指标不得混入标准评分或填成零。
- [ ] 参考固定 skills 方法时将样本数、抖动门禁和工具容量限制作为协议/版本配置，验证执行的门禁；manifest 自报硬件频率不能冒充服务观察。

## Validation

合成 trace 回归重复 kernel、部分输出和解析错误；真实 CPU Program 测试工具失败与产物导出，NPU 测量由 22 执行。

**Completion gate:** CPU 工具/解析路径通过；不以此宣称 NPU 时延等价。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
