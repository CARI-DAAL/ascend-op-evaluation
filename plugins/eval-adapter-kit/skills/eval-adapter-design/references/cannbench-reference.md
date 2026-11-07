# CANNBench 作为通用能力的参考实例

本文件是方法映射示例，不是 adapter 实现或完整覆盖认证。来源固定为 cann-bench `f0488d95b4d44a6a0da1b8cd99e91fbd06181962`；其他版本重新核对。该快照 framework VERSION=1.0.0，tasks VERSION=2.0.0；A3-2.0 alias 不能替代实际环境和数据身份。

## 如何映射

| 上游配置/行为示例 | 通用能力 | adapter 的工作 |
| --- | --- | --- |
| task-dir/operator/case-id、task schema/attributes | 准备数据 | 选择任务并绑定材料；保留输入/输出参数语义 |
| eval_seed、input_dist、value range、get_input | 准备数据 | 映射生成器及其参数；区分未提供与随机 seed |
| source_build_args、build_timeout_sec、skip-install | 构建加载 | 传 argv/预算/产物与安装策略；不操作共享宿主环境 |
| golden_precision、oracle/bench/get_output | 执行 | 选择参考函数、精度和输出处理方法 |
| checker_name、precision_thresholds、输出契约 | 比较 | 选择比较方法与阈值；完整保留特殊值/回退语义 |
| warmup/repeat、profiler_level、freq boost、perf_metric_strategy_override | 测量 | 配置 collector/conditioning/reducer，不改变指标含义 |
| input rotation、accuracy retry、batch/memory、profiler retry | 数据/执行/测量组合 | 保持时序和实际消费位置，受总预算约束 |
| device、processes_per_card、max_cases_per_task_unit、case isolation | 执行资源 | 映射已预留设备与任务内并发，不私占其他卡 |
| tensor cache dir/mode/tasks | 准备数据/产物 | 固定缓存身份，显式 miss/require 行为 |
| op guard、ACL launch、msprof export | 执行/诊断 | 声明工具/运行方式与能力；特殊策略可由独立方法包执行 |
| baseline、score、agent/model labels、report format | 外部 adapter | 汇总、判分和展示，服务保留原始方法结果 |

这只是分组示例。完整盘点应读取 [Config](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/config.py)、[BenchConfig](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/registry/bench_registry.py)、[CLI](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/cli.py)、[staged 入口](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/staged_eval.py)、[任务 schema](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/benches/cann_spec.py)、wrapper、环境读取及实际消费代码。

## 保持方法，不只复制数字

该快照 CANN 默认 checker 使用高精度 golden/同精度参考与相对误差方法，另有小值域、相消、整数、bit-exact 和特殊值分支。通用 allclose 加两个阈值不能自动等价。可复用足够表达这些语义的公共方法；不够时运行固定上游 checker 方法包，仍由同一执行能力承载。

默认性能使用 torch_npu.profiler、warmup=3/repeat=5 和 kernel_details CSV。当前实现按 step 累加同名 kernel 的所有 launch，再对每个 kernel 跨 step 取中位数后相加。不要替换成 Event 或另一种平均/中位数公式。源码：[比较](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/utils/compare.py)、[采集](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/eval/perf_eval.py)、[聚合](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/base/perf_strategy.py)。

skills 的 msprof application、msprof op、深度指标是其他协议。特别是“每轮序列总和的中位数”与“各 kernel 中位数之和”不等价；诊断/插桩运行不充当标准 timing。参考 [固定 skills profiling](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ops-profiling/SKILL.md)。

## 服务充分性的判据

固定范围内每项参数都能通过上述能力表达，有实际消费者、合法值与拒绝行为，并通过变值/交互及上游差分测试，才证明覆盖。这个过程不需要服务理解 CANNBench 的名字。源码盘点和映射示例不等于当前服务已支持全部参数。
