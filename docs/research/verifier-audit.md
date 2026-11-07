---
status: current
applies_to: source-review
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# Triton verifier 第一性原理审查：PLE 的启发与本仓库的差距

调研日期：2026-11-04。代码基线：`bc22bacf51a659438dd28439644cc7d96f93382b`。本次只增加调研报告，未修改运行代码。审查范围覆盖输入协议、correctness engine、结果整形、性能门禁、profiler 解析及隔离边界；不是完整安全审计。

**结论：部分符合，但目前不能把 verifier 的通过当作可信的算子正确性认证，更不适合作为无需额外防护的对抗式 agent 奖励裁判。** 服务层的证据管理、失败分类和正确性优先设计较扎实；判定核心存在可复现的错误接受，执行状态也未充分隔离。优先修补裁判的判定能力，再扩展测试分布与性能可信度。

本仓库当前是调用方提供 reference/workloads/candidate 的开发评估服务，不是持有独立题库的正式 benchmark：新 admission 只允许 trial/rollout，历史 grade 仅支持恢复。因此，缺少隐藏题库应视为外部评估协议的能力边界；而下述输出漏检、输入污染和数值比较缺陷，在开发评估场景同样需要修复。依据：[admission.py](../../packages/ascend-op-eval/src/ascend_op_eval/control/admission.py) L40–55、[输入架构](../explanation/evaluation-lifecycle.md)。

## 1. 从 PLE 可以迁移什么

[Mercor 原文](https://www.mercor.com/blog/introducing-physical-engineering-s-last-exam-ple-with-google-cloud-ai-research/)强调：平均满足大量约束，并不意味着设计整体可行；只有硬约束全部通过，才值得奖励成本优化。对应算子，是先确认接口、语义、数值与执行约束成立，再讨论加速比。

不能把这一原则简化成“任何失败总分都必须为零”。[PLE 官方规则](https://github.com/google-research/ple/blob/main/docs/rules.md)对含约束与优化目标的任务使用 `s = 0.4 p + 0.6 G O'`：硬约束失败会关闭优化项，但仍保留约束分；另有 rubric 类任务。本文不建议照搬这套权重，只借鉴“诊断进展与优化资格分开”。

[论文 v2 §3.2、§5.1](https://arxiv.org/html/2610.30537v2)描述了独立真值审计、Creator–Solver 对抗构建和隔离的 grader；[artifact 流程](https://github.com/google-research/ple/blob/main/docs/artifacts.md)要求在干净环境重新判交付物并抽样复跑。这启发我们分别检查：参考答案是否可靠、执行是否相互独立、裁判权限是否独立、结果是否可重放。实际 PLE 任务 grader 位于需申请访问的数据集，本次未取得；这里引用论文和官方协议，不声称审计了全部 PLE grader。

以下是本次对算子验证的推导，而非 PLE 对 Triton 的规定：对契约允许的输入域 D、实现 K 和参考 R，需要检验 `Contract(K,x) ∧ NumericalPolicy(K(x),R(x)) ∧ ExecutionPolicy(K,x)`。测试只能为抽样集合提供证据，不能证明整个 D。有效 speedup 还要求完整正确性覆盖，以及同一测量口径下的可信分子和分母。

## 2. 已做对的部分

| 原则 | 实现证据 | 判断 |
| --- | --- | --- |
| 正确性先于比较性能 | [evaluation.py](../../packages/ascend-op-eval/src/ascend_op_eval/evaluators/evaluation.py) L310–319：comparison 要求 correctness succeeded 且 outcome=correct | 符合；门禁本身不弥补裁判的假阳性 |
| 部分成功不能冒充整体成功 | [shaping.py](../../packages/ascend-op-eval/src/ascend_op_eval/evaluators/shaping.py) L473–488；[选择覆盖测试](../../tests/test_correctness_controls.py) | 符合；selected-only 成功仍可为 incomplete |
| 缺失证据不能成为通过 | [evaluators/verify.py](../../packages/ascend-op-eval/src/ascend_op_eval/evaluators/verify.py) L285–310；[shaping.py](../../packages/ascend-op-eval/src/ascend_op_eval/evaluators/shaping.py) L445–453 | 符合；基础设施错误与候选错误分开 |
| 浮点允许有理由的容差，同时保留硬限制 | [engine/verify.py](../../packages/ascend-op-eval/src/ascend_op_eval/engine/verify.py) L949–1018；[_official_tolerance.py](../../packages/ascend-op-eval/src/ascend_op_eval/engine/_official_tolerance.py) | 有基础；默认 90% matched ratio 还同时要求逐元素 allclose 和 MERE，不能说它允许 10% 任意错误 |
| baseline 来源独立 | [evaluators/baseline.py](../../packages/ascend-op-eval/src/ascend_op_eval/evaluators/baseline.py)：reference-only 测量、核对返回分母、候选不能更新缓存 | 方向正确 |
| 宿主隔离与持久化边界 | [sandbox 文档](../explanation/execution-isolation.md)、[正确性证据](../../packages/ascend-op-eval/src/ascend_op_eval/execution/correctness_evidence.py)、[结果收集测试](../../tests/test_engine_result_collection.py) | 已有 manifest/source binding、lease fencing、拒绝 symlink 结果等保护；不等于进程内裁判隔离 |

CPU-first 不自动等于数学真值：设备、算法和累积顺序会改变舍入。应区分“兼容指定 NPU reference”与“贴近高精度数学结果”两种目标；不能在候选失败后挑选更易通过的参考。当前 `_try_run_case` 对数值 mismatch 不切换设备，是正确设计。[PyTorch 2.9 数值说明](https://docs.pytorch.org/docs/2.9/notes/numerical_accuracy.html)、[verify.py](../../packages/ascend-op-eval/src/ascend_op_eval/engine/verify.py) L1380–1410。

## 3. 已复现的缺陷

以下使用真实 `torch==2.9.0+cpu` 调用当前 engine；没有修改其实现。它们证明比较/解析逻辑有缺陷，不代表已通过完整 HTTP、AST 退化检查及真实 NPU 链路重现每种情况。P0 指修复前不应据此声称可信判分；P1 指重要的数值或测量有效性缺陷。

### P0：输出类型或结构不符合契约时，可能完全跳过比较

[run_single_case](../../packages/ascend-op-eval/src/ascend_op_eval/engine/verify.py) L1208–1244 只在一对输出**都是 Tensor**时调用 `compare`，没有拒绝其他类型的分支。

复现结果：reference 返回 `tensor([2.,2.])`，candidate 返回 Python `0`，函数正常返回；`7` 对 `-999`、内容不同的两个 dict，也正常返回。即使协议仅支持 Tensor，正确行为也应是明确拒绝非 Tensor，不能跳过检查。

建议：先校验完整输出树的结构与叶子类型；不支持的类型明确报错。支持 scalar/list/tuple/dict 时递归校验每一叶子，所有 mismatch 都形成可归因的失败证据。

### P0：默认分支没有强制输出 dtype 一致

[compare](../../packages/ascend-op-eval/src/ascend_op_eval/engine/verify.py) L844–934 检查 shape，但默认计算路径没有 dtype gate。reference 返回 float32 `[2,2]`、candidate 返回 float16 `[2,2]`，实际被接受。声明 tolerance 和 non_compute 分支已有 dtype 检查，因此问题具体在默认路径。

建议：把 shape、dtype、输出设备/布局等契约检查放在数值分流之前。reference 可以在 CPU，candidate 输出仍应遵守所声明的目标设备；stride/alias 是否必须相同则取决于算子契约。PyTorch 自带比较工具支持递归结构和默认 dtype 检查，可作为基础组件参考，不应不加配置地替代现有数值协议。[PyTorch 2.9 testing](https://docs.pytorch.org/docs/2.9/testing.html)。

### P0：用输入 dtype 推断“量化”，会接受错误索引

[compare](../../packages/ascend-op-eval/src/ascend_op_eval/engine/verify.py) L923–930 将 float 输入、int 输出统一送入 `|diff| <= 1`。但 argmax、topk 的索引和 searchsorted 等不是量化值。

复现：输入 `[0.,10.,1.]`，正确 argmax 为 `1`，候选返回 `2`，实际被接受。建议由可信契约显式区分 index、count、quantized value 等输出语义；索引默认严格相等，只有明确允许时使用量化误差。同一个多输出算子需要逐输出策略，不能靠最高输入 dtype 一刀切。

### P0：嵌套输入共享存储，候选可改变 reference 将要读取的值

[run_single_case](../../packages/ascend-op-eval/src/ascend_op_eval/engine/verify.py) L1178–1194 只复制顶层 Tensor；list 中的 Tensor、可变容器直接共享，而且 candidate 先运行。

复现：输入 `[[tensor([3.])]]`，reference 语义为 `2*x`，应为 `[6.]`。candidate 先把 list 内 Tensor 清零，再返回 `[0.]`；随后 reference 也读取零，检查通过，原输入也已变为零。

建议：从可信输入快照构造两份独立执行状态，递归处理容器和张量；保留契约允许的内部 alias/view 关系，不能简单逐 Tensor clone 后改变题意。分别验证输入副作用；禁止变更时对快照比对，允许 inplace 时比较规定的后状态。缓存与非缓存路径应具有相同语义。

### P1：比较器自身会丢失信息或溢出

1. [_compare_quant_fp_to_int](../../packages/ascend-op-eval/src/ascend_op_eval/engine/verify.py) L697–700 使用 int64 subtraction/abs。`golden=0`、`actual=-2**63` 的差值溢出为负，`diff > 1` 为假，实际被接受。建议采用不会溢出的边界比较；严格整数 equality 无须通过减法实现。
2. [_official_tolerance.compute_error_stats](../../packages/ascend-op-eval/src/ascend_op_eval/engine/_official_tolerance.py) 将两端转成 float32；默认 `_compute_accuracy_state` 也这样做。float64 `1e8` 对 `1e8+1`，声明零 atol/rtol/cap 且 matched ratio=1，实际仍通过，因为差异先被转换消除了。对于不支持的 dtype 应提前拒绝；支持时误差计算不能降低其所需精度。这是 CPU 比较器复现，不声称所有 Ascend 设备都支持该 dtype。

上游兼容测试证明“复刻了上游规则”，并不证明规则对所有 dtype 和输出语义都正确。建议保留显式命名的兼容协议，另行版本化严格语义协议，避免无声改变历史 benchmark 定义。

### P1：profiler 对重复同名 kernel 少算时延

[parse_operator_latency](../../packages/ascend-op-eval/src/ascend_op_eval/engine/benchmark.py) L437–450 按 Name 分组后只取最后 `active_count` 行，隐含每次算子调用每个 kernel 名只出现一次。

复现：1 次 warmup、3 次测量；每次调用同名 kernel 两次，每次 10µs，共 8 行。正确的每次算子 kernel-sum 为 20µs，解析结果为 10µs。若两端调用次数不同，加速比会发生系统性偏移。

建议按迭代/调用关联划定 active window，再加总其全部 launch；不能仅靠 Name 推断迭代边界。同时将 kernel-sum 与 Event 调用窗口作为不同测量定义，禁止把 kernel-sum 直接描述为端到端延迟。已有 Event warmup、同步、中位数和 CV 检查值得保留。

## 4. 结构性差距：静态确认，未进行完整攻击或实机验证

**裁判和候选仍共享 Python 执行权限。** `_load_verify_modules` 在同一解释器中导入 reference 与 candidate，`run_single_case` 同进程运行并比较；宿主读取的 `verify_result.json` 在该 attempt 的可写目录内。Bubblewrap 主要保护宿主、其他 attempt 和设备可见性；readonly engine 文件不保护已加载 Python 对象。AST 退化检查检查 Triton 定义、调用及部分禁用运算，不是判分完整性的安全边界。依据：[verify.py](../../packages/ascend-op-eval/src/ascend_op_eval/engine/verify.py) L1247–1266、L1446 起；[validate_triton_impl.py](../../packages/ascend-op-eval/src/ascend_op_eval/engine/validate_triton_impl.py) L741–767；[sandbox 文档](../explanation/execution-isolation.md)。

如果目标包含不可信 agent 搜索，应让可信控制器拥有输入快照、reference 结果、比较器与最终 verdict；候选只在隔离 runner 中产出受验证的输出数据。反序列化不能执行候选代码，候选写出的统计/JSON 不应成为最终判分权威。reference 源码公开并非天然错误，关键是候选不能改变其执行状态或借其代做计算。对严格对抗场景，需进一步证明进程、权限、IPC 和设备内存边界，而非只加一个 subprocess。

**公开固定 workload 的证据边界有限。** 当前默认 seed=200，调用方提交 workload、reference 和 tolerance；tolerance 数值刻意与上游保持一致、不做范围校验。开发调试可接受这种自由，但外部可信评估方必须冻结任务、有效输入域和数值政策，不能让被评分候选自行放宽规则。多种随机分布和 custom generator 不等于已自动覆盖边界。依据：[operator_input.py](../../packages/ascend-op-eval/src/ascend_op_eval/operator_input.py) L163–179、L386、L454；[input_generation.py](../../packages/ascend-op-eval/src/ascend_op_eval/execution/input_generation.py)。

建议在声明域内增加评估方持有的多 seed、tail/边界 shape、允许的非连续布局、重复索引、极值及数值性质测试。合法按 shape 专门化应保留；不要用超出题目契约的隐藏输入否定正确实现。用“已知正确实现 + 故意错误实现”的成对语料校准 false accept/false reject，优先纳入本报告反例。

**性能复用仍依赖运维约束。** `BaselineCache.key_for` 包含 reference/protocol/namespace，但不直接包含设备型号、runtime/build 或时间；record 无时间戳，使用 hsetnx 保留初值。配置注释要求硬件/计时运行时改变时人工轮换 namespace，不能把它描述成已自动绑定全部环境。可增加显式环境 binding、age 和定期 fresh paired calibration。依据：[baseline_cache.py](../../packages/ascend-op-eval/src/ascend_op_eval/execution/baseline_cache.py)、[config.py](../../packages/ascend-op-eval/src/ascend_op_eval/config.py) L33–34。这是测量风险，不是本次已测得的真实漂移。

**实机覆盖不能从 CPU tests 推断。** 仓库已有 add smoke、官方 BatchMatmul 51 workloads 和独立 Event/profiler 入口；[NPU 验证计划](../development/npu-validation.md)明确区分已有实现、待补测试与待执行硬件验收。本次没有运行 NPU，因此没有给出设备正确性、性能稳定性或实际部署隔离合格结论。

## 5. 建议实施顺序与验收标准

1. **先修判定核心**：输出树、dtype、逐输出语义、嵌套输入独立性、整数溢出和误差精度；将上述反例加入真实 Torch 回归。验收须同时包含正例，避免用“全部拒绝”换取零假阳性。结构/type 失败要正确归因为候选错误。
2. **建立可信判分边界**：对不可信候选隔离 reference/comparator/result authority；验证候选不能改变 reference、比较函数或最终结果。适配明确的任务契约，并记录威胁模型。
3. **修复性能计量**：覆盖重复同名 launch、多 kernel、条件 launch，核对 Event 与 profiler 各自定义；绑定 baseline 环境并支持新鲜配对测量。正确性通过不能替代计时有效性。
4. **由上层补独立验收协议**：冻结 contract、seed 策略、容差和版本；加入契约内隐藏输入与 mutant corpus；在目标 NPU 上通过 HTTP 完整链路重跑。协议变化升级 correctness/benchmark 版本及 evaluator build，避免重用旧通过证据。

## 6. 本次验证与重现

环境：已有 `/tmp/triton-eval-baseline-venv/bin/python`，Python 3.12、Torch `2.9.0+cpu`。没有安装或修改依赖。

现有相关测试 **183 passed**（一个 FastAPI/Starlette 弃用警告）：

```bash
python -m pytest tests/test_verify_engine.py tests/test_official_tolerance.py \
  tests/test_correctness_controls.py tests/test_correctness_evidence.py \
  tests/test_benchmark_gate.py tests/test_benchmark_event_stats.py \
  tests/test_benchmark_kernel_metrics.py tests/test_reference_policy.py \
  tests/test_engine_result_collection.py -q
```

额外探针包含两个控制项：正确 add 通过，明显错误的 Tensor add 被 AccuracyError 拒绝。在此基础上，8 个错误正确性案例被接受，另一个 profiler 案例实际输出 0.01ms，预期 0.02ms。现有测试全绿与这些缺陷可以同时成立，因为测试没有覆盖相应反例。

以下脚本从仓库根目录运行。它观察当前行为，不是已加入测试套件的正式回归；修复后应把错误案例改成要求拒绝的断言。`accepted` 表示对应 engine 函数未抛异常，不是 HTTP/NPU 认证结果。

```python
"""Read-only CPU probes of the checked-out verifier; no NPU claim."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import torch
from ascend_op_eval.engine import verify, benchmark

results = []
def probe(name, fn):
    try:
        detail = fn()
        results.append({'probe': name, 'observed': 'accepted', 'detail': detail})
    except Exception as exc:
        results.append({'probe': name, 'observed': 'rejected', 'error': type(exc).__name__})

class Model(torch.nn.Module):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
    def forward(self, *args):
        return self.fn(*args)

def run(ref, candidate, inputs):
    verify.run_single_case(verify.ModelPair(Model(ref), Model(candidate), 'cpu'),
                           inputs, 'cpu', verify.CaseContext(1, 1))

probe('control_correct_add', lambda: run(lambda x: x + 1, lambda x: x + 1, [torch.ones(2)]))
probe('control_wrong_tensor', lambda: run(lambda x: x + 1, lambda x: x + 10, [torch.ones(2)]))
probe('tensor_replaced_with_python_scalar', lambda: run(lambda x: x + 1, lambda x: 0, [torch.ones(2)]))
probe('wrong_python_scalar', lambda: run(lambda x: 7, lambda x: -999, [torch.ones(2)]))
probe('wrong_nested_dict', lambda: run(lambda x: {'y': x + 1}, lambda x: {'y': x + 10}, [torch.ones(2)]))
probe('wrong_output_dtype', lambda: run(lambda x: x + 1, lambda x: (x + 1).half(), [torch.ones(2)]))
probe('argmax_index_off_by_one', lambda: run(lambda x: x.argmax(), lambda x: x.argmax() + 1,
                                            [torch.tensor([0., 10., 1.])]))

def mutation():
    xs = [torch.tensor([3.])]
    def candidate(values):
        values[0].zero_()
        return torch.zeros(1)
    run(lambda values: values[0] * 2, candidate, [xs])
    return {'original_input_after_candidate': xs[0].tolist(), 'correct_output_before_mutation': [6.]}
probe('nested_input_mutation_changes_reference', mutation)
probe('float64_error_lost_in_fp32', lambda: verify.compare(
    torch.tensor([1e8], dtype=torch.float64), torch.tensor([1e8 + 1], dtype=torch.float64), torch.float64,
    tolerance={'max_atol': 0., 'max_rtol': 0., 'required_matched_ratio': 1., 'max_error_cap': 0.}))
probe('quant_int64_overflow', lambda: verify.compare(torch.tensor([0], dtype=torch.int64),
    torch.tensor([-2**63], dtype=torch.int64), torch.int64, verify.InputSpec('float', torch.float32)))

def profiler():
    with tempfile.TemporaryDirectory(prefix='ple-profiler-probe-') as temp:
        # 1 warmup + 3 measured calls; same kernel launches twice per call, 10 us each.
        Path(temp, 'kernel_details.csv').write_text('Name,Duration(us)\n' + 'kernel,10\n' * 8)
        _, latency = benchmark.parse_operator_latency(temp, 1, 3, keep_res=True)
        return {'reported_ms': latency, 'expected_ms': 0.02}
probe('profiler_same_kernel_twice_per_invocation', profiler)
print(json.dumps({'torch': torch.__version__, 'results': results}, indent=2))

```
