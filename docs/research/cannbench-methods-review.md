---
status: current
applies_to: source-review
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# AscendC 正确性与性能方法审查

日期：2026-11-06。审查对象为本地执行核心设计、tickets，以及 `cann/cann-bench` 的固定源码提交 `f0488d95b4d44a6a0da1b8cd99e91fbd06181962`。本轮没有构建上游工程或运行 NPU。

## 审查结论

核心执行能力与外部判定规则分离是可行方向，但原 tickets 对具体评测方法写得不够明确：

1. **AOE-11 是原生工程执行的 tracer，不能单凭构建成功和 exit=0 宣称 AscendC 正确。** 需要一个方法已固定的正确/错误样例作为执行证明；完整 CANNBench 判定属于 AOE-13/23。
2. **AOE-18 不能只写“支持 profiler”。** 必须记录采集工具、数据源、测量窗口、launch 归属、聚合公式、同步与缓存策略；Event、kernel-sum 和端到端时间不互相替代。
3. **上游规范与当前实现有差异。** 固定版本的代码、实际选用配置和原始产物才足以定义复现目标，不能按一段概述自行重写算法。
4. **`cannbench-a3-2.0` 尚不是已验证线上环境。** 此提交的根 VERSION 为 `1.0.0`，tasks/metadata/VERSION 为 `2.0.0`，任务文件注明 requires-framework >=1.0.0。框架版本、任务版本、工具链和硬件必须分别记录。

版本来源：[framework VERSION](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/VERSION)、[tasks VERSION](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/tasks/metadata/VERSION)。

## 1. CANNBench 的实际正确性方法

对于 CANNBench profile，外部 adapter 应打包并运行固定上游 harness，不调用本服务现有 Triton verifier 替代它。

调用链主要为：任务/case 与参数构造 → golden/oracle 与 native reference → 候选执行 → 输出契约检查 → RelativeErrorChecker → compare_tensors → case 结果与评分。

### 参考实现与输入

- 默认 `BenchConfig.golden_precision=fp64_cpu`，另有 `native_cpu`、`native_npu` 策略；不是所有任务都可无条件改成 FP64。
- oracle 优先使用任务 `<op>_oracle`，否则 plain golden；同精度参考优先 `<op>_bench`，否则 plain golden。native 策略可复用对应 golden。
- 任务的 get_input/get_output hooks、optional outputs、输出 dtype 声明、ignore indices 及算子级阈值都参与语义，不能只保存随机 shape 和一个全局 tolerance。
- 默认 seed 为 0，浮点分布默认 uniform；任务自身可以限定值域/生成方式，必须固定实际生效配置。

来源：[BenchConfig](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/registry/bench_registry.py)、[Evaluator](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/eval/evaluator.py)、[Config](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/config.py)。

### 数值与结构判定

先进行真实输出类型及 proto 输出 dtype 契约检查，再调用该任务选择的 checker。默认 CANN checker 是 RelativeErrorChecker。

普通浮点路径将高精度 golden 截断到目标输出 dtype 后升回 FP64，候选也转换到 CPU FP64，用以下相对误差统计量进行基础判断：

```text
g = cast_to_output_dtype(golden), represented in FP64
r = abs(actual - g) / (abs(g) + 1e-7)
MERE = mean(r)
MARE = max(r)
base pass: MERE < threshold and MARE < 10 * threshold
```

典型默认阈值为 FP16 `2^-10`、BF16 `2^-7`、FP32 `2^-13`；允许固定快照定义的任务级覆盖。

这不是完整算法。实现还包含小值域、相消、同精度参考正常域误差等分支，按 ErrorCount 规则判断；整数走精确比较；零阈值浮点可走 bit-exact。NaN 位置、Inf 符号与饱和边界也有专门处理。adapter 要复用这些代码和其版本，不能把方法简化为 torch.allclose 或只计算两个数字。

特别地，固定快照包含某些 Inf/有限值不一致时的饱和边界处理，以及全非有限匹配时的兼容行为。记录这些是为了保持 benchmark 语义，不代表它们是所有任务应采用的通用数值规则。

来源：[AccuracyEvaluator](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/eval/accuracy_eval.py)、[compare.py](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/utils/compare.py)、[thresholds.py](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/utils/thresholds.py)。

## 2. CANNBench 的实际性能方法

### 采集

当前默认路径使用 `torch_npu.profiler`，默认 Level1、warmup=3、repeat=5。具体请求可以覆盖，因此 profile 必须保存有效参数。

单 case 路径包括 warmup/频率准备、正式 step 前清 L2、候选调用、同步、profiler step 推进和导出。代码明确在 `prof.step()` 前同步设备，避免异步直调 kernel 落在采集窗口之外。采集或导出失败要保留错误，不能以进程返回成功代替有效性能证据。

性能调用使用 InputPool/CallInputPool 轮换张量地址，降低按 data_ptr 缓存结果造成的假快；harness 使用实际候选调用的输出进行精度检查。精度阶段通过不能替代测量调用的输出有效性。新输入复检、batch case 采集和回退路径也须按冻结配置保留，不自行改动。

来源：[perf_eval.py](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/eval/perf_eval.py)、[input_pool.py](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/eval/input_pool.py)、[启动脚本](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/scripts/run_evaluation.sh)。

### 权威数据源和聚合

默认 `KernelDetailsStrategy` 以 **kernel_details.csv 为 elapsed_us 的唯一权威来源**。trace_view 用于补充指标或 sanity check，不在 CSV 缺失时静默取代它。

典型有 cache-clean 标记的流程按标记切分 measurement step，剔除框架 warmup/cache-clean kernel。每个 step 内，同名目标 kernel 的所有 launch duration 先求和；然后每个 kernel 名分别跨 step 取中位数；最后累加各 kernel 的中位数。batch 路径还验证预期标记数量、时间顺序和 warmup/repeat 划分。

```text
duration_per_kernel_per_step[k, s] = sum(all launches of k in step s)
T_cand = sum_k median_s(duration_per_kernel_per_step[k, s])
```

它不等价于“每轮全部 kernel 总和的中位数”。例如两种 kernel 各三轮为 A=[1,100,100]、B=[100,1,100]，前者得到 200，后者得到 101。保持兼容需要连聚合顺序一并固定。

单 case parser 在没有 warmup/cache 分隔符时存在 Step Id/Task ID 回退路径；因此关闭 cache-conditioning 不只是性能条件变化，也可能改变序列归属前提。这种配置要单独差分验收，不能笼统宣称同一种可比测量。

源码：[perf_strategy.py](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/base/perf_strategy.py)。

### 文档与代码的差异

同一快照的 benchmark_spec §4.5 仍描述从 chrome trace 的 dequeue 事件取得 kernel 时间；实际默认 strategy 明确采用 CSV，并指出按旧 trace 名称识别可能漏掉自定义 AscendC kernel。BenchConfig 部分注释也仍保留“trace_view 为主”的旧说明。

本次采用实现调用链作为复现依据，并显式记录矛盾；不能根据这段规范另写一套 trace parser 冒充上游结果。来源：[规范](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/docs/spec/benchmark_spec.md)、[实际 strategy](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/base/perf_strategy.py)。

## 3. msprof 与 Event 的位置

| 路径 | 数据与用途 | 与 CANNBench 默认分数的关系 |
| --- | --- | --- |
| torch_npu.profiler + KernelDetailsStrategy | 固定配置的 NPU kernel CSV 采集及上游聚合 | 本次快照的默认评测路径 |
| msprof export summary | 从 PROF 原始数据导出 op_summary CSV | 上游 MsProfSummaryStrategy 使用；不能静默替换默认评分来源 |
| msprof application / msprof op / 深度计数器 | 由各工具/recipe 定义序列测量或瓶颈诊断 | 需要独立方法身份，详见 skills 方法审查 |
| torch.npu.Event / 对应 ACL Event | stream 有序的设备时间区间 | 是另一种测量口径，不自动等同 kernel-sum |
| 进程 wall time | 构建/执行与服务端到端开销 | 不作为 kernel latency |

上游 `_export_msprof_summary` 会在选用对应 strategy 时调用 `msprof.py export summary`；正式默认 KernelDetailsStrategy 与基线采集用 MsProfSummaryStrategy 的 fallback 规则不同。不能因为二者都产生 CSV，就认为测得的指标可互换。

Event 测量尤其需要确认 AscendC 的实际 launch stream。若扩展使用自己的 ACL stream，只在 Torch 当前 stream 上记录 start/end，随后全设备 synchronize，不能补救结束 Event 没有覆盖目标工作的事实。adapter 必须建立明确的 stream 依赖或选择能覆盖目标执行的其他测量协议。

本地已有 [msprof op 执行器](../../packages/ascend-op-eval/src/ascend_op_eval/engine/msprof_op.py) 和 [deep 执行器](../../packages/ascend-op-eval/src/ascend_op_eval/engine/msprof_deep.py)，可作为外部诊断程序迁移基础。但 [profile runner](../../packages/ascend-op-eval/src/ascend_op_eval/engine/profile_runner.py) 仍从 Triton 装饰器提取 kernel 名，不能直接当作已支持 AscendC 的完整入口。

## 4. Adapter 的方法清单

每个 adapter/profile 必须冻结并输出以下方法身份，服务只保存其材料与运行事实：

- task/version、candidate sources/binary、oracle/native/generator 的源码摘要。
- 有效 seed、输入分布、case 选择和输入/输出契约。
- golden_precision、checker、阈值/特殊值策略与覆盖选项。
- collector、数据源、profiler level/metric group、有效 warmup/repeat、batch 设置。
- stream/synchronize 规则、conditioning/cache 清理、输入池与测量输出复检。
- 目标 kernel/launch sequence、归属方式、聚合公式、单位及 baseline/scoring 来源。
- 实际设备、工具链/工具版本、原始采集数据、导出完成状态与缺失项。

普通 AscendC 任务可以选择任务自己的 golden 与数值契约；原生 smoke 至少应有已知正确输出与故意错解的对照。CANNBench profile 则使用固定上游程序完成上述流程。不能依据候选语言自动选择容差，也不能只因编译/运行成功就判正确。

## 5. 对 tickets 的修订

保持 24 票和现有依赖，不把数值规则放回核心：

- AOE-11：原生 smoke 增加明确方法身份、golden 和错解拒绝，区分执行成功与验证通过。
- AOE-13：固定并验证上游有效 golden/checker/perf strategy；以上述提交作为已审查的候选基线，而非宣告网站版本映射已证明。
- AOE-18：明确 benchmark、msprof sequence timing、op/deep 诊断与 Event 的独立口径，覆盖同步和重复 launch。
- AOE-22/23：验证异步直调、自有 stream、原始产物有效性以及直接上游/服务路径的一致性。

方法代码核对不能代替实机结论。实际 NPU 时延、工具兼容、采集权限和线上 profile 一致性仍需设备验收。
