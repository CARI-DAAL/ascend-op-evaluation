你是本仓库的开发 agent。请实际完成自定义评测方法接入，让外部 adapter 能提交并运行版本化的 checker、测量方法或完整评测 harness。不要停留在方案、文档、schema 或占位接口。

Historical implementation record. Current interface and qualification are documented in the guides and support matrix; this record retains its original acceptance scope.

工作目录：
/home/yubaifeng/e84381970/projects/triton-op-agent/tools/triton-op-evaluation

一、先核查现状

读取当前 HEAD、git status 和适用的 AGENTS.md，保留用户已有修改。不要假定历史描述仍然准确，已有实现应复用并验证。

必读：
- docs/proposals/execution-core/capabilities.md
- docs/proposals/execution-core/README.md
- docs/research/cannbench-methods-review.md
- docs/research/verifier-audit.md
- plugins/ascend-op-eval-adapter-kit/skills/eval-adapter-design/references/capability-contract.md
- triton_evaluation/api/contract.py
- triton_evaluation/api/routes.py
- triton_evaluation/runtime/native_candidate.py
- triton_evaluation/engine/native_support.py
- 当前 worker、admission、lease/fencing、恢复及相关测试

docs/plans/ascend-op-eval/ 中的计划可作参考，但本次范围以本 prompt 为准。不要求顺带完成全仓更名、所有 24 张票或无关架构迁移。

二、目标和职责

实现真实的端到端链路：
方法包封存 → 方法解析与参数校验 → 提交 → worker 执行
→ 保存报告与原始产物 → 查询、取消和恢复。

服务负责：
- 方法包身份、参数与能力校验。
- 输入和产物管理。
- 资源、隔离、期限、取消、恢复。
- 可复用的比较、测量方法和明确的结果协议。

外部 adapter 负责：
- CANNBench 任务解析、hooks、默认值及 override 优先级。
- 上游方法选择、参数映射、profile。
- baseline、HAP 评分和任务报告。

服务核心不得导入 CANNBench，也不得添加 benchmark 名称分支。完整上游 harness 可以作为方法包运行。

三、必须交付的能力

1. 方法包和方法描述

支持独立打包的实现及其必要资源，定义并实现：
- 不可变 method_ref。
- 实现、依赖、descriptor 的摘要及版本。
- 执行入口。
- 参数 schema、默认值和约束。
- 输入、输出及原始产物契约。
- runtime、工具和设备要求。

别名必须在 admission 时解析并冻结。服务进程不得通过导入用户方法包来读取元数据。

明确区分 adapter 可提交的材料与部署方可登记的 runtime/权限。依赖必须可追溯，不得污染共享宿主环境。

2. 参数和执行身份

拒绝未知参数、非法组合、未知方法和不满足的能力要求。
正确区分未提供、0、false 和 null。

记录 requested/effective 参数；方法、依赖、输入、有效参数及相关环境身份必须进入执行身份与适用缓存键。不得跨方法复用旧的正确性或时延证据。

不得接受参数后忽略，也不得静默回退成 native_tensor_v1、其他 collector 或其他聚合方式。

3. 自定义 checker

外部 adapter 能指定 checker 方法包及参数，并在 worker 上执行。
提供明确的数据传递和输出契约，能表达实际输出、参考输出，以及方法所需的附加参考或元数据。

结果必须区分：
- 比较通过。
- 比较不通过。
- 方法异常或超时。
- 输入/输出协议错误。
- 环境能力不足。

不能通过把 checker 塞入 candidate.forward 来冒充方法接入。
候选自行写出的 pass 不得被提升为服务认证的正确性证据。明确实际隔离保障，不能把同进程执行宣称为裁判隔离。

4. 自定义测量

允许方法控制必要的 warmup、repeat、同步、采集和聚合流程。
结果保存单位、方法身份、有效参数、样本和必要原始 profiler 产物。

至少证明：
- 现有内建测量仍可使用。
- 外部方法能够采用不同聚合规则，并实际改变结果。
- 重复同名 kernel、多 kernel、条件 launch 的归属和统计不会被错误合并。

CANNBench 的统计规则必须核对固定上游源码后实现，不得用现有“每次调用 kernel 总时长取平均”代替上游规则。

5. 生命周期和兼容性

复用现有 durable admission、队列、租约、attempt fencing、deadline、取消及 owner 恢复机制，不新增独立任务状态机。

方法的子进程、重试和采集步骤均受父预算约束。
过期 attempt 不得发布结果。
日志和产物必须有边界、身份及明确的缺失/截断状态。

现有 API 默认行为和历史记录读取保持兼容；新增契约显式版本化，不给旧记录补字段后冒充新证据。

6. 客户端与示例

提供实际可运行的客户端调用和文档：
- 打包或上传方法。
- 指定方法、参数和输入提交。
- 查询、取消、恢复。
- 读取报告与原始产物。

至少交付一个外部 checker、一个外部测量方法，以及固定版本 CANNBench 的接入示例。示例不能依赖手工修改服务源码。

四、实施顺序

先列出现状与目标的简短差异，然后直接实施：

1. 用真实 CPU 子进程打通最小纵向链路。
2. 接入 checker、测量和结果协议。
3. 补齐身份、恢复、取消、隔离及兼容性。
4. 接入固定上游 CANNBench。
5. 执行 CPU、NPU 和上游差分验收。

优先复用现有实现。为完成能力所必需的重构可以做，但避免无关更名和大规模迁移。持续更新实施状态，不要只写计划后结束。

五、验收标准

通过公开接口验证，而不只是单元测试内部函数：

- 自定义 checker 确实被调用；修改其有效参数能改变预期判定。
- 自定义测量确实被调用；受控样本下不同聚合规则得到预期结果。
- 未知参数、方法摘要不匹配、缺依赖、输出不合规、缺环境均明确失败。
- 方法或参数变化不会复用旧证据。
- 正常完成、非零退出、超时、取消、worker 丢失、恢复、过期 attempt 写入均有行为测试。
- 既有 native/Triton 路径及历史结果读取通过回归。
- 多文件原生工程在真实 NPU 上完成构建、正确性和测量。
- CANNBench 固定同一上游 revision、任务、配置和环境，对比直接上游执行与经服务执行的结果。

CANNBench 覆盖正常、错误、边界精度、复合输出、构建/运行失败，以及多 kernel 测量；具体 case 以固定上游实际支持范围为准。

性能容差在运行对照前确定，保留两侧原始记录。CPU mocks、skip、exit=0 都不能替代真实设备和上游一致性验收。

缺设备或上游材料时，完成不受阻的开发与 CPU 验证，准确列出未验证项目和解除条件。不得把“代码完成”写成“CANNBench 已完备”。

六、交付报告

最终明确给出：
- 实现的接口和调用示例。
- 关键文件及行为变化。
- 实际运行的测试、结果与跳过项。
- 方法包版本、参数和产物追溯方式。
- CANNBench 参数/行为覆盖矩阵：已实现且验证、已实现待验证、未支持。
- 剩余限制及兼容性影响。

分别回答：
1. 自定义方法接入是否端到端可用？
2. 固定公开 CANNBench 快照的哪些能力已经验证？
3. 还有哪些缺口，能否声称覆盖该快照？

本轮执行开发和测试；不自动生产切流、公开发布、推送远程或删除历史数据。不要重复询问已明确的设计方向和常规实现选择。
