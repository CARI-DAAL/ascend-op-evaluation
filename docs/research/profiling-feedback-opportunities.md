# Eval service 的 profiling 反馈可以怎样改进

## MindStudio 能提供哪些证据

MindStudio Agent 的算子 profiler skill 先识别上板或仿真、输入形态以及目标，再按需选择采集和解释方法。可将这一做法用于 eval worker 的能力探测和指标选择。LoopEngine 每轮可以只消费与当前决策有关的一条发现及其证据，完整材料留作按需读取。官方 skill 里的 Top 5 是报告模板，适合人工阅读。[MindStudio Agent 官方 skill](https://github.com/Ascend/msagent/blob/master/skills/operator/msot-msopprof-operator-profiler/SKILL.md)

针对周报所称 A5，应先核对 worker 实际 SoC 和安装版本。官方上板指南把 warp 流水图支持范围列为 Ascend 950PR/950DT。对已确认走 SIMT 的热点 kernel，可先检查 warp 持续时间分布；需要解释差异时，再尝试 PcSampling，按 PC 和 stall 原因统计样本，例如 scoreboard 等待或 warp 同步。建议同时返回命中次数、总样本数、kernel 启动序号和采集模式。该 warp 流水图由独立 replay 插桩生成，绝对耗时有扰动。普通 InstrTimeline 看不到 SIMT VF 内部指令。[msOpProf 上板指南](https://github.com/Ascend/msopprof/blob/master/docs/en/user_guide/msopprof_user_guide.md)

建议把两个问题分开验证。对已有 SIMT 路径，trace 可以定位长尾 warp，PC 样本可以定位等待集中在哪些指令；要追到具体代码，需保留同一次编译的二进制、调试位置映射及可用 IR。对没有观察到 SIMT 事件的路径，先核对采集覆盖和产物中的执行模式。若热点仍走 SIMD，可把 SIMT 改写列为草图候选，用同 shape、dtype、精度约束下的无插桩耗时验证收益。缺少采样或源码映射时应显式报告证据缺口。Triton Ascend 文档也区分了模拟器 trace 的指令流水和可关联源代码的可视化产物。[Triton Ascend profiling 指南](https://github.com/Ascend/triton-ascend/blob/main/docs/en/debug_guide/profiling.md) · [msOpProf 代码热点图](https://github.com/Ascend/msopprof/blob/master/docs/en/user_guide/msopprof_user_guide.md#operator-code-hot-spot-map)

## Eval service 的具体改进顺序

核对版本为 `4b8c075430b61e597a97b587a38f5a2a9e75206b`。下列源码观察针对内置 evaluation 的 trace/op/deep 路径。自定义方法可以有自己的采集协议。用户提供的周报用于选择验证场景，其中的十分钟与算子收益没有作为本服务基线。

### P0 · 缩短首份反馈，保住已经采到的证据

已有联合 timing/trace、按 case 和指标组选择以及逐核采样开关。旧版 A3 的两例 add 实验里，event 联合执行将首份 performance 中位数从 24.4 s 提前到 20.0 s，整轮从 45.9 s 降到 32.9 s。原始报告尚未入库，event 逐例耗时比在 0.773–1.21 之间。建议直接复用联合链路，用 correctness 筛掉错误候选，用同协议 timing 找到回退或收益空间最大的代表 shape，再用 trace 的 kernel 耗时占比选择一例定向 deep。访存假设先选 PipeUtilization 和 Memory，怀疑核间失衡时再开逐核采样。case 选择策略留在调用方，并在诊断结果中显示覆盖范围。[实测记录](feedback-performance.md#9-npu-实测记录2026-10-14分析机-atlas-800t-a3) · [现有执行协议](../explanation/measurement-evidence.md)

op/deep runner 已在每个 case 后写 snapshot，但 evaluator 收到退出码 124 或超时时先返回基础设施错误。大 shape 排在最后时，前几例采完也无法通过这条路径返回。建议每完成一例发布绑定 attempt 的已验证诊断快照，保留终态 timeout、剩余 case 和未完成 pass，仅对缺口重采。先用“两例完成、第三例超时”覆盖超时、被新 attempt 替换、同一 case 重试三种情况，检查旧 attempt 的证据不会写进新结果。[runner](../../packages/ascend-op-eval/src/ascend_op_eval/engine/profile_runner.py) · [evaluator](../../packages/ascend-op-eval/src/ascend_op_eval/evaluators/profile.py)

### P0 · 让多 kernel 热点和归因可以复核

deep 在首个有匹配值的指标组里选单次耗时最大的记录，再到其他 pass 以完整 Op Name 匹配，各取最长记录。假设 A 调用十次、每次 8 µs，B 调用一次、耗时 20 µs，当前选择会指向 B，但 A 占这两者累计设备时间的 80%。建议先在有效测量窗口记录 launch 顺序、次数、累计耗时、最大单次耗时和流，再按用户目标选热点。并发流的累计耗时仅用于排序，判断端到端收益还需要依赖关系和关键路径。跨 pass 若同名 launch 无法对齐，报告歧义，并保留各 pass 的观测。[deep 选择逻辑](../../packages/ascend-op-eval/src/ascend_op_eval/engine/msprof_deep.py) · [上游 launch 映射调研](cannbot-methods-review.md)

每个 case 的原始 op/deep 采集目录目前是临时目录。公开 deep 结果可以携带指标，但将每条 recommendation 投影成文本，丢失该建议自身的 evidence/source 关联。建议在目录释放前按需归档最小证据，给每个 finding 返回 case、构建摘要、kernel/launch、观测值与单位、证据位置和待验证假设。CSV 用文件摘要加行列，trace 用文件摘要加 stream、时间区间或事件标识，IR 用同次构建的文件摘要加操作位置。空泡只有起止事件时只能定位现象；要指向编译根因，还需对应指令或 IR 的依赖链以及更改后的同条件复测。缺文件时返回缺哪份、下一步怎么采。分析可在离线端重放，同一次采集能支持多个归因规则。仓库已有针对 probe 导出的摘要校验重放脚本，以及规定标准 artifacts 返回的 AOE-18，可沿用其机制。[公开投影](../../packages/ascend-op-eval/src/ascend_op_eval/evaluators/shaping.py) · [重放脚本](../../scripts/replay_profiler_export.py) · [AOE-18](../plans/ascend-op-eval/issues/18-measurement-profiler-programs.md)

### P1 · 给 LoopEngine 返回可排序、可淘汰的候选

服务提供观测与产物，adapter 解释硬件和算子语义，LoopEngine 决定改什么及何时停止。每个优化候选附影响范围、预期改变的指标、复测 case 和既往试验结果。对串行无重叠片段，占总耗时 p、局部加速 s 时，总体加速上界可按 1/(1−p+p/s) 估算。例如占比 5% 的片段即使耗时降到零也只有约 1.053×，有助于解释周报中局部优化过细的问题。草图效率可同时报告有效计算量、最低搬运量、适用引擎峰值和带宽来源，用 max(F/P, B/BW) 给出指定假设下的理想时间下界。未知流量、缓存层次或混合引擎使模型失配时，明确缺项。候选进入下一轮须通过独立正确性验证，并用原 benchmark 协议确认收益。[上游成本模型及适用条件](cannbot-methods-review.md)

### 验收实验

固定设备、工具链、输入、正确性门槛和总 NPU 分钟，对比纯 loop、现有 profiling loop、分层采集加证据引用的 loop。用 scatter 与 groupnormswish 观察前期收敛及后期反超，用 convstandard2d 和 GroupedMatmulSwigluQuantV2 检验跨 shape 排序，用大 shape 超时、重复同名 launch、导出为空检验部分反馈。A5 另加有已知 SIMT 路径与无 SIMT 路径的配对样例。对每组记录提交至首份可行动反馈的 p50/p95、采集有效率、每条定位可回查率、经人工或对照实验确认的归因比例，以及固定预算下最佳正确候选的同协议加速比。先用既有产物盲回放检查热点与误报，再上机校准计时漂移；准确率与覆盖率分别报告，允许返回证据不足。待累积可复核的候选及结果后，再评估贝叶斯优化或知识图谱的增量收益。

## 从 MindStudio 借鉴的通用设计

**让下一次采集回答一个能改变决策的问题。** 官方 skill 先判断目标和已有产物，无数据时给最小采集命令和下一步，需要解释结果时才出诊断。msOpProf 提供 BasicInfo、按需指标和 launch 范围选择。eval 已有 case、metric group 和逐核开关；建议由 LoopEngine 先消费现有结果，再表达待区分的假设，由 adapter 选择兼容的最小补采。验证时比较得到同一条正确结论花费的 NPU 秒数和首份反馈时间。[MindStudio skill 执行协议](https://github.com/Ascend/msagent/blob/9ffb1c767b3147cd6e4c5525143ee602dd0438e4/skills/operator/msot-msopprof-operator-profiler/SKILL.md#执行协议) · [msOpProf 参数及筛选顺序](https://github.com/Ascend/msopprof/blob/ce5a1158cebf0ba3b9f8a48793304660c22ece36/docs/en/user_guide/msopprof_user_guide.md#tool-usage) · [eval 的测量边界](../explanation/measurement-evidence.md)

**相同指标名的两次观测，能否比较取决于实验条件。** msOpProf 提供 kernel、application 和 range 重放；文档明确 kernel 与 range 会清 L2，application 保留 L2。对依赖上游数据复用的 kernel，两次缓存命中率可能同时真实，直接相减却会误导优化。建议 adapter 在 profile 结果中声明真实测量窗口、重放粒度、预热和已知缓存策略。LoopEngine 只有在实验条件相容时才展示趋势，算子收益用既有 benchmark 协议复验。[msOpProf 重放与预热说明](https://github.com/Ascend/msopprof/blob/ce5a1158cebf0ba3b9f8a48793304660c22ece36/docs/en/user_guide/msopprof_user_guide.md#command-reference)

**让优化建议能追到一条观测，也允许没有建议。** skill 分别记录关键数据、瓶颈的判断依据和影响、建议对应的瓶颈及前提，证据不足可标待确认。eval 已有按累计耗时选出的热点；公开 deep 结果目前把每条 recommendation 投影为字符串。最小改进是在保留现有文本的基础上，把一个建议绑定到 case、kernel、pass 和已有指标来源，并说明还缺什么才能下结论。例如搬运管线忙可以触发一次带宽采集；达到带宽瓶颈需要同范围的实际带宽与参照值。验收可抽检证据引用的可回查率，以及缺数据时是否仍错误输出确定根因。[官方报告字段](https://github.com/Ascend/msagent/blob/9ffb1c767b3147cd6e4c5525143ee602dd0438e4/skills/operator/msot-msopprof-operator-profiler/SKILL.md#固定报告模板默认用于结果分析) · [eval 的公开结果投影](../../packages/ascend-op-eval/src/ascend_op_eval/evaluators/shaping.py)

**同一份输入应能重复分析。** 官方 skill 将运行 application、用 config 和对象文件构造采集、用 simulator export 解析已有 dump 列为不同输入形态。后者是已有数据进入分析流程的具体先例。eval 的 op/deep 会释放每例临时采集目录，可先按需保留小型 summary 和完整性摘要，用同一份数据离线验证新归因规则；详细 trace 再按预算保留。重算规则可评估算法变化，设备侧收益仍需重新测量。[MindStudio skill 输入约束](https://github.com/Ascend/msagent/blob/9ffb1c767b3147cd6e4c5525143ee602dd0438e4/skills/operator/msot-msopprof-operator-profiler/SKILL.md#使用本技能时的硬规则) · [eval 临时采集目录](../../packages/ascend-op-eval/src/ascend_op_eval/engine/profile_runner.py) · [已有 probe 重放工具](../../scripts/replay_profiler_export.py)

一个可以直接回归的覆盖问题出现在内置 op 模式。标准请求没有暴露 launch 采集上限，带明确 kernel 名的路径在未指定内部 launch_count 时把限制交给工具。上述版本的 msOpProf 指南给出的默认上限是 1，解析器在已导出的行有效且无警告时可给出 complete。消费方需要区分“已捕获记录的指标齐全”和“覆盖了这个 case 的目标调用”。首个验收样例可以让同一 case 依次发射 A 和 B，仅采 A，检查响应是否写明采集窗口、有效上限、观察数以及覆盖是否已知，并确保 LoopEngine 不会据此给 A 标注整个 case 的耗时占比。[op 采集与解析](../../packages/ascend-op-eval/src/ascend_op_eval/engine/msprof_op.py) · [msOpProf 参数](https://github.com/Ascend/msopprof/blob/ce5a1158cebf0ba3b9f8a48793304660c22ece36/docs/en/user_guide/msopprof_user_guide.md#command-reference)
