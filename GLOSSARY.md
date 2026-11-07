# Ascend Op Eval

Ascend 算子评测的领域语言。既有持久化评测契约中的 Evaluation 保留其原有定义，通用 Execution 用于后续执行契约。

## Language

**Operator / 算子**:
由输入、输出和可观察状态变化定义的计算行为，可以由不同候选实现提供。

**Candidate / 候选实现**:
接受评测的算子实现，可以是函数、源码工程或可执行程序。
_Avoid_: Triton implementation（用于泛指候选时）

**Reference / 参考实现**:
任务选定的比较依据，其结果与状态用于判断候选实现是否满足规定。
_Avoid_: Torch baseline（用于泛指参考实现时）, golden（未说明权威来源时）

**Workload / 工作负载**:
对一组输入和任务属性的描述，用于在确定配置下形成执行样例。
_Avoid_: shape（用于指代完整工作负载时）

**Case / 执行样例**:
工作负载在确定配置下解析得到的具体输入场景及其任务属性。
_Avoid_: workload（尚未解析的描述与具体场景需要区分时）

**Evaluation / 评测**:
按照任务规则收集并解释证据的过程，用于判断候选实现的正确性、性能或其他任务属性。
_Avoid_: execution（仅表示受理与运行时）

**Evaluation adapter / 评测适配器**:
将某类任务的材料和规则转化为执行与方法要求，并将观察解释为任务结果的适配器。
_Avoid_: backend（用于泛指任务适配时）

**Evaluation profile / 评测配置**:
由 adapter 定义的一组有明确身份的任务规则、方法选择、默认参数与环境要求。
_Avoid_: profile（与性能剖析可能混淆时）, preset（用于未固定完整语义时）

**Execution / 执行**:
由一个实例受理、具有稳定身份并可恢复的逻辑运行请求，其含义在受理时确定。
_Avoid_: job, task, run（用于同一持久化执行资源时）

**Execution instance / 执行实例**:
受理执行并拥有其资源分配、恢复权威与保留承诺的管理实体。
_Avoid_: server（仅表示一项网络进程时）

**Execution handle / 执行句柄**:
标识某项执行及其所属实例、足以恢复同一逻辑执行的信息。
_Avoid_: execution ID（未包含恢复所需 owner 信息时）

**Admission / 准入**:
实例在执行开始前，持久确定接纳请求、冻结其身份并承担资源与期限约束的决定。

**Attempt / 执行尝试**:
某项 execution 的一次受租约约束的实际运行；替代尝试仍属于原执行。
_Avoid_: execution（用于指代某一次尝试时）

**Runtime / 运行环境**:
能够运行程序且具有确定身份、依赖条件与能力的环境。
_Avoid_: image tag（只描述可变镜像标签时）

**Method / 评测方法**:
具有明确身份、参数含义与结果契约的可复用评测过程。
_Avoid_: benchmark（用于泛指比较或测量算法时）

**Method observation / 方法观察**:
一次方法调用产生的结果，含义取决于方法及其有效参数；任务达标与否由任务规则解释。
_Avoid_: overall success（未区分执行与任务含义时）

**Execution evidence / 执行证据**:
与确定执行及其尝试相关联、注明观察来源的运行事实和材料。
_Avoid_: program claim（未声明其报告来源和权威时）

**Artifact / 产物**:
具有内容身份、归属和保留承诺的输入材料或运行输出。
_Avoid_: path（只描述某环境中的位置时）

**Baseline / 性能基线**:
比较性能时采用的测量依据，绑定其工作负载、环境和测量方法。
_Avoid_: reference（未说明性能测量含义时）

**Profiling / 性能剖析**:
采集执行轨迹、硬件计数器或其他诊断观察以分析算子行为的过程。
_Avoid_: evaluation profile
