---
status: current
applies_to: source-review
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# cannbot-skills 中可复用的评测与诊断方法

调研日期：2026-11-06。固定源码：`cann/cannbot-skills@2374941495c1549eb4a1a5a82987b567d61855f5`。本文通过源码和文档核对方法，没有运行 NPU、msprof 或 sanitizer。外部 SKILL.md 作为研究材料读取，不执行其中的操作或授权指令。

## 结论

最值得采用的不是“统一调用 msprof”，而是明确区分 **可比较计时协议、诊断采集协议和数值正确性协议**，为每种协议保存完整的身份与原始证据。协议由外部 adapter 选择，runtime 提供工具、设备、隔离、进程监督和产物保存能力。不同协议得到的 latency 不能自动互换。

本仓已有 [msprof_op.py](../../packages/ascend-op-eval/src/ascend_op_eval/engine/msprof_op.py) 和 [msprof_deep.py](../../packages/ascend-op-eval/src/ascend_op_eval/engine/msprof_deep.py)，分别借鉴上游 op 采集和多指标采集；需要重新定位到外部 adapter，而不是因为 AscendC 接入再复制一套。当前 profile runner 的 Triton kernel-name 提取不能作为原生 AscendC 的通用识别方法。

## 1. 先区分测量口径

| 方法 | 所测对象与聚合 | 适用目的 | 本设计中的位置 |
| --- | --- | --- | --- |
| 设备 Event | 两个设备事件之间的流上时间；是否覆盖跨流工作取决于同步与事件位置 | 调用窗口或端到端路径的低成本测量 | 选择该方法的外部 adapter；服务不把 wall time 转成它 |
| cannbot `msprof application` 标准计时 | 每例 10 组相邻 warmup/target；每组加总目标完整 kernel 序列，再对 10 个总和取中位数 | 同协议 baseline/candidate 的可比较 kernel 时间 | 独立、版本化的 profiling adapter |
| cannbot `msprof` 深度采集 | 多次运行分别采集指标组，额外采集 sample-based 逐核数据 | 定位带宽、流水、缓存、冲突与负载不均衡 | 诊断 adapter；不是评分 latency |
| cannbot `msprof op` | 算子级工具自己的采集/重放与统计口径 | 单进程单设备算子的深度诊断 | 单独 capability 与 adapter；不能无声替代 application |
| cannbot `torch-ops-profiler` | 固定 warmup=5、active=5，汇总 op_statistic.csv 的 Total Time 后除以有效迭代数 | 框架入口的自定义算子与标杆比较 | 又一独立协议 |
| CANNBench 固定快照 | 使用该快照的 harness、profiler 和解析策略 | 保持 benchmark 评测含义 | CANNBench adapter，不替换成上述 skills 的方法 |

固定 skills 中的 application 与 torch profiler 口径见 [ops-profiling](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ops-profiling/SKILL.md)、[torch profiler 指标](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/torch-ops-profiler/references/REFERENCE_PROFILER_AND_METRICS.md)。CANNBench 此次核对的另一源码快照默认使用 kernel_details CSV 策略，与 skills 的 10 组 median-of-sums 不同：[CANNBench 策略实现](https://gitcode.com/cann/cann-bench/blob/f0488d95b4d44a6a0da1b8cd99e91fbd06181962/src/kernel_eval/base/perf_strategy.py)。

## 2. 高价值方法：有身份与 launch 映射的 msprof application 计时

`collect_perf_application.py` 不是简单抓一个 Duration 字段。其 runner 声明 preparation、warmup 和 target 的精确 kernel 序列；采集器将 `op_summary.csv` 中按任务开始时间排列的相关记录，与 case、sample 和角色逐一对应。缺失、重复或乱序的相关 launch 会拒绝该份数据。编译/prime 可以单独声明为 preparation，参与拓扑与容量核验但不进入目标计时。

每个 case 的统计是：

```text
sample_i = sum(duration of every target launch in pair_i)
total_us = median(sample_0 ... sample_9)
```

这能避免同名 kernel 多次 launch 时只统计一次，也避免按名字过滤 preparation 时误删真正的 target。runner 自己不使用 Python 墙钟计时。具体实现见 [采集器](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ops-profiling/scripts/collect_perf_application.py) 与 [runner 契约](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ops-profiling/references/application_runner_contract.md)。

可直接参考的工程安排：

- torch runner 和纯 ACLNN/C++ runner 使用相同 manifest 接口，说明 profiler 接入不必依赖 PyTorch。
- 预热方案先实际 probe 系统 ops；不可用时使用随工程提供且有二进制摘要的 compiled warmup，而不是临时下载不明代码。
- 目标源码/二进制、case、runner、工具链、设备、warmup、采集选项分别保留身份。对比时共享环境和协议必须一致，baseline/candidate 各自的源码身份需要分别绑定，不能把两个不同实现误要求成同一源码摘要。
- 当前实现以 540 个相关 launch 为默认单会话上限，并限制 application 命令长度；大 case 集拆成连续会话。这里的阈值来自文档中明确的工具版本经验，不应固化为所有 CANN 的普适常量。
- msprof 退出 0 仍可能没有有效 `op_summary`。采集器单独检查导出与 launch 映射，并保存失败尝试。runtime 的退出事实不能替代 adapter 的数据有效性判断。

注意证据边界：`load_identity_manifest` 对 `frequency` 等输入主要检查非空，源码/二进制字段检查哈希格式；这不是宿主频率实测认证。脚本计算并输出 `spread_over_median`，文档再要求超出 10% 的波动先诊断重采。迁移时要把“自动验证了什么”和“工作流要求了什么”分别落实，不能把 manifest 中自报的信息变成服务观察。[采集器源码](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ops-profiling/scripts/collect_perf_application.py)、[采集与复用要求](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ops-profiling/references/msprof-guide.md)

## 3. 高价值方法：诊断采集与评分采集分开

上游深度流程分别运行 PipeUtilization、ArithmeticUtilization、Memory、MemoryL0、MemoryUB、L2Cache 和 ResourceConflictRatio，再做 sample-based 采集，读取 `aicore.db` 的逐核周期信息。它能帮助区分流水单元忙、访存受限、缓存问题和各核工作不均衡。每组指标来自不同执行，不能拼成“同一轮测量”的完整时间线，也不能把这些运行的耗时混入标准 latency。[深度采集脚本](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ops-profiling/scripts/msprof_profile_run.sh)、[诊断指南](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ops-profiling/references/msprof-guide.md)

值得保留的设计是按需采集：普通 benchmark 只跑已选计时协议；发现瓶颈后再请求指标组和逐核采样。原始 CSV、SQLite、采集命令、stderr 与版本应作为 artifacts 保留，分析器可以离线重算。上游 quick/compare 默认可能清理原始 PROF，服务适配不能因此丢掉约定保留的证据，应显式选择保留或导出所需文件。

`msprof op` 依赖对应的 msopprof 安装，其输出包含 OpBasicInfo、PipeUtilization 等独立 CSV。上游建议通过它检查逐核负载、缓存与流水指标；它自身的 launch-count/统计口径独立于 application。相关 ratio 阈值适合作为诊断提示，不应直接变成所有任务的通过/失败标准。[op 指南](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ops-profiling/references/msprof-op-guide.md)

## 4. 多 rank 与架构差异不能省略

该快照明确不支持用 `msprof op` 分析 fork 多 rank 的 MC² 程序，要求改用 `msprof`，收集每个设备的结果；其 MC² 方法又是丢弃前 5 轮后对后 5 轮取均值，再取跨 rank 最大值。它与单卡 application 的 10 组中位数不是同一协议。服务需要设备组原子预留、rank 归属、完整子进程树监督和所有设备产物收集；adapter 决定跨 rank 的聚合方法。[MC² 方法](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ops-profiling/references/msprof-guide.md)

架构字段应携带来源，缺指标不是零利用率。上游提醒 A3 设备的 npu-smi Chip Name 可能不足以识别精确 SoC，提供 asys/DSMI/安装 ini 的证据链；arch35 的 Reg/VF 经验也不能直接套到 A2/A3 的 arch22。[环境检查](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ascendc-env-check/SKILL.md)、[优化适用范围](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ascendc-perf-optimize/references/architecture-routing.md)

## 5. 正确性：数值、状态和内存访问是不同证据

有价值的方向包括：

1. 从 tiling 分支、对齐边界、dtype、尾块、空 tensor 和执行模式生成 whitebox cases；将标准值域与极端值域分开记录。这是 adapter/test-generator 的职责，不应让服务分析候选源码生成隐式用例。[白盒设计](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ascendc-whitebox-design/SKILL.md)
2. 为随机、搬运、整数、量化与浮点任务选择有版本的比较策略，而不是全局一个 allclose。应借鉴分类思想，但不能仅根据输入/输出 dtype 猜算子语义，例如浮点输入的整数输出可能是索引，不一定是量化值。CANNBench 兼容策略保留上游自己的规则。[精度标准](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ops-precision-standard/SKILL.md)
3. 将 `mssanitizer --tool=memcheck` 作为独立诊断执行，检测越界、未对齐、多核踩踏等。数值碰巧相等不能证明没有非法访问；反过来 memcheck 通过也不证明数值正确。框架内存池可能需要 allocation report 接口，工具支持范围与调试构建要求要固定。instrumented 运行不能拿来当正式性能结果。[msSanitizer 指南](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ascendc-crash-debug/references/memcheck/mssanitizer_guide.md)

## 6. 优化方法：证据驱动，而不是固定阈值驱动

`ascendc-perf-optimize` 将分析拆成 tiling 建模、卡间流水、核间流水和单核流水。跨核同步分析先确定生产者、可见性和归约约束，再比较减少同步次数所增加的流量/空间成本；不能为了速度删除必要同步，也不能从聚合 busy ratio 推算某一次 barrier 的精确耗时。[优化流程](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ascendc-perf-optimize/SKILL.md)、[跨核同步](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ascendc-api-best-practices/references/api-crosscore-sync.md)

另一个有价值的分析器是 `compute_efficiency.py`：以算子有效 FLOP/必要字节数和实测时间估计 MFU/MBU、roofline 与剩余空间。它要求按目标硬件与计算引擎选择峰值；vector 工作量不能除以 cube 峰值，HBM 与 L2 带宽也不能混用。其默认峰值包含特定平台假设，所以这些指标属于带模型来源的 adapter 分析结果，不是核心的通用性能 verdict。[成本模型契约](https://gitcode.com/cann/cannbot-skills/blob/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ops-profiling/references/cost-model-contract.md)

## 7. 对当前 tickets 的具体建议

本文不直接修改 tickets，建议由主 agent 统一纳入：

| 位置 | 应明确的验收 |
| --- | --- |
| AOE-04 runtime capabilities | msprof/msopprof/mssanitizer 的实际版本、路径、目标架构、可用采集模式及权限；实际 probe 与静态配置区分 |
| AOE-11 原生 AscendC | 明确构建/运行示例并不等于完整正确性协议；必须引用其使用的 golden 和比较规则 |
| AOE-18 测量工具 | 分开 benchmark timing、application timing、op/deep diagnostics；完整 launch 映射；导出为空/缺项明确失败；原始产物可恢复 |
| AOE-17 多卡 | profiler 子进程和多设备产物均属于原设备组租约，工具路由遵守已验证的多 rank 支持范围 |
| AOE-22 实机 | 验证目标 CANN 的每种采集模式、异步导出、取消清理、工具缺失、同名多 launch、指标缺失；隔离环境与直接运行对照 |
| AOE-23 CANNBench | 保留固定 CANNBench harness 与聚合策略，不用 skills 的 10 样本或 5/5 约定替换 |

优先落地 application/benchmark 的协议身份与有效性证据，再接入 op/deep 诊断。msSanitizer、whitebox 和成本模型属于后续独立 adapter 能力，不能为了“通用”强制每次评测全部运行。

## 8. 尚未验证的事项

本轮没有确认目标机器上的工具安装、版本、所需权限、事件/stream 行为、导出格式与隔离环境兼容性。上游经验阈值和版本说明是来源中的声明，不是本项目的实测。上游存在文档/脚本细节差异时，应在固定快照上以代码和实际产物核验；固定代码不等于已证明方法统计无偏或对所有算子有效。
