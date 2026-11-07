---
status: proposed
applies_to: design
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# 六项通用评测能力与外部 adapter

状态：修订设计，尚未实现。2026-11-06。本文是当前职责划分的依据；[执行核心设计](README.md)保留资源、隔离和恢复细节。

## 第一性原理

算子评测的共同过程是：准备输入，把实现变成可调用对象，执行它，检查结果，测量耗时，需要时诊断原因。不同 benchmark 改变的是具体函数、方法和参数。

因此服务提供六项可复用能力，外部 adapter 负责把任务翻译成这些能力的组合。既不要求每个 adapter 重写所有比较器与 profiler，也不把 CANNBench 的规则和参数名固化进服务。

| 能力 | 通用输入与参数 | 产出 |
| --- | --- | --- |
| 准备数据 | 数据 artifact 或生成函数；seed、shape/dtype、分布、attributes | 输入及其身份；需要时包含状态快照 |
| 构建加载 | 源码/预构建产物、工具链、构建命令与参数、入口 | 可执行对象、构建日志、产物身份 |
| 执行 | 函数/可执行入口、输入、设备/进程、预算、同步要求 | 输出、状态变化、退出与异常事实 |
| 比较 | actual/reference、输出契约、比较方法及精度参数 | 判定、误差统计、差异位置与覆盖 |
| 测量 | 可调用对象、采集方法、warmup/repeat、conditioning、归属与聚合参数 | 有方法身份的时延/样本及原始数据 |
| 诊断 | 可执行入口、msprof op/deep/sanitizer 等工具、指标和范围 | trace、硬件计数器、内存检查与诊断报告 |

六项是职责，不要求六次 HTTP 请求或六个进程。输入已经给定时无需生成；预构建产物可以跳过编译；诊断按需运行。reference 与 candidate 都使用执行能力，但 adapter 决定参考函数、精度和状态隔离。

## 服务与 adapter 的划分

服务包含执行内核和通用方法模块。执行内核负责环境、资源、隔离、超时、幂等、恢复、产物。通用方法模块提供可复用的生成/构建/执行/比较/采集实现，接受明确参数。

外部 adapter 拥有任务格式、case 选择、profile/defaults、上游 hooks、方法选择与参数映射，以及基线、评分和任务报告。CANNBench adapter 不进入服务源码，也不成为服务安装依赖。

通用方法可以提供 exact、bit-exact、allclose、相对误差等比较，Event/profiler 等测量；复杂特殊逻辑由独立函数或方法包扩展。服务不需要因为一个 benchmark 新增阈值或 checker 就增加名称分支。

## 参数可变，方法含义明确

每次调用指明方法及版本、parameters、输入引用和必要资源；方法声明参数 schema、默认值、约束和输出含义。用户可以调整参数，但请求实际采用的值必须可见、可追溯。

- 通用方法不要求所有任务使用同一 tolerance、采样次数或统计量。
- 未知字段、非法组合和缺失能力明确拒绝，不能接收后忽略。
- zero/false/null 与未提供不同；保留上游默认值/override 的真实优先级。
- 有效配置、方法实现/依赖、输入/源码和环境共同参与身份。
- 服务保存通用方法输出，adapter 决定它对应任务的 verdict 和 score。

高层评测请求由同一执行内核落实，不另建一套排队/租约状态机。已有通用程序执行可作为扩展入口，但不能仅凭“任意代码都可跑”就声称已提供了六项可复用方法。

## CANNBench 参数为什么能覆盖

参数去向只有几类：

| CANNBench 行为 | 通用去向 |
| --- | --- |
| task/case 选择、profile 与评分 | adapter |
| seed、输入分布、task attributes、get_input | 准备数据及生成函数参数 |
| build args、安装、入口 | 构建加载 |
| golden precision、oracle/native hooks | 执行参考函数及其配置 |
| checker、阈值、特殊值/回退规则 | 比较方法参数或自定义 checker |
| warmup/repeat、profiler level、cache、batch、input rotation、聚合 | 测量方法及其过程配置 |
| device/processes、timeout/retry、内存 | 通用资源与预算；方法内控制受父预算约束 |
| msprof/export、guards、工具模式 | 诊断/执行方法与 runtime 能力 |
| 输入缓存、基线和原始数据 | artifact 与 adapter 的缓存/评分策略 |

这张表解释能力为何足够表达这些变化，不是所有参数已实现的证明。外部 adapter 对固定上游版本逐项列参数、消费位置和测试；CLI、config、env、task schema、hooks 与动态注册都要盘点。值合法但部署没有工具/硬件时，明确返回能力不足。

CANNBench 的具体比较/测量语义参见[源码方法审查](../../research/cannbench-methods-review.md)。不能仅复制两个精度值和 warmup/repeat，就宣称榜单一致；完整输出契约、参考精度、特殊值、同步、launch 归属、聚合与基线都属于该 profile。

## Adapter 交付与验收

每个 adapter 交付一份简洁规范：任务来源和范围、六项能力组合、参数对应表、有效配置与方法身份、结果解释、失败行为和差分验收。

逐参数变值证明实际生效，测试关键交互，再对照直接上游执行。strict profile 只允许声明过的覆盖；其他合法变更属于 custom 实验。公开源码快照、真实硬件和线上隐藏配置的验证范围分别报告。

设计指导和模板打包在项目插件 [eval-adapter-kit](../../../plugins/ascend-op-eval-adapter-kit/README.md)。插件是设计工具，不是 CANNBench 实现，也不声明这些新接口已经上线。

## 既有计划的调整

24 张 tickets 的资源/恢复工作继续适用，但实施时以上述职责为准：

- AOE-02/09：在已有 execution 底座上定义方法调用和参数校验，不只交付裸远程命令。
- AOE-10/12：默认 adapter 选择规则；服务通用比较方法复用算法，任务默认值不固化其中。
- AOE-11/18：构建、执行、测量与诊断以通用能力实现，外部示例组合验证。
- AOE-13/23：外部 CANNBench 参数映射和差分验收；服务中没有专属 adapter。

本轮只更新设计、计划和项目 skill 插件，不实现或发布评测服务。
