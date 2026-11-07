---
status: current
applies_to: design
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# Ascend Op Eval：项目命名、仓库与文档体系重构 proposal

状态：accepted，2026-11-06 用户确认实施。设计保留原评审基线；当前交付范围与后续功能见[迁移说明](../../migration/rename-and-cutover.md)。
调研基线：本地 `2bdca53` 及当前工作区；已有未提交设计和计划一并作为输入。
范围：定义目标结构、命名契约、文档归属与迁移门槛。本次交付为 proposal，尚未实施代码迁移或部署更名。

推荐将产品、仓库和主发行名统一为 **`ascend-op-eval`**，展示名为 **Ascend Op Eval**。
以“算子评测需要可信、可恢复的执行与证据”为起点，重新组织执行底座、通用方法和外部 adapter。
文档按读者任务与知识状态组织，代码按职责和独立发布需求组织。

## 1. 为什么需要整体重构

当前名称承载了不同历史阶段的含义：

| 已观察到的情况 | 具体位置 | 造成的问题 |
| --- | --- | --- |
| 仓库叫 `triton-op-evaluation`，发行包叫 `triton-evaluation`，import 叫 `triton_evaluation` | 根 README、`pyproject.toml`、源码目录 | 用户难以判断是否支持 AscendC、原生工程和自定义方法 |
| 插件叫 `triton-eval`，但说明和代码已包含 native candidate | `plugins/triton-eval/` | 插件名限制了实际能力的理解 |
| 新材料又使用 `ascend-op-evaluation` | `plugins/ascend-op-eval-adapter-kit/plugin.json` | 同一个目标项目出现第三种仓库拼写 |
| 服务使用 `TRITON_EVAL_*`，客户端使用 `EVALUATION_*` | `config.py`、两份 `.env.example`、插件 CLI | 调用与部署配置缺少一致规则 |
| `service/runtime/evaluators/engine` 交叉承载编排、执行和评测语义 | `triton_evaluation/` | 新方法和新任务容易继续加进服务专属链路 |
| 当前架构、未来设计、源码调研同时位于 `docs/architecture/` | 执行核心设计、六项能力、CANNBench 方法审查 | 导航中的“Understand the implementation”无法明确表示哪些已经实现 |
| 长期维护的实施规范位于 `.scratch/`，公开文档反向依赖它 | `docs/development/agent-workflow.md`、`docs/README.md` | 临时材料实际承担正式规范和任务状态来源 |
| 文档、CLI 和部署说明使用不同版本线索 | workflow 名中的 v2、文档中的 v2.1、`versioning.py` 中的 legacy | 读者容易把历史标签理解为已实现的版本协商 |

最后一项尤其需要按代码校准：当前 `versioning.py` 对外声明的 API/storage 是 `legacy`，不能仅凭文件名把新协议记为已支持。
本提案依据本地实现与材料，不重新认证研究文档中的外部源码结论。

## 2. 从第一性原理推导项目边界

一次算子评测需要回答三个不同问题：

1. **执行发生了什么？** 哪个程序、输入、环境和设备，在什么预算与隔离条件下运行，如何结束，留下哪些产物。
2. **如何获得观察？** 如何生成数据、构建加载、执行、比较、测量与诊断；方法实际采用什么参数。
3. **这些观察对任务意味着什么？** 哪些 case 必须通过、用哪个 reference、采用什么默认值、如何计分、是否满足某个 benchmark。

对应三类职责：

| 职责 | 拥有的内容 | 变化原因 |
| --- | --- | --- |
| Execution | 准入、幂等、持久化、调度、attempt、租约、隔离、期限、取消、产物、恢复 | 基础设施与资源能力变化 |
| Methods | 六项能力的参数化实现、方法描述、参数约束、观察结果与方法身份 | 比较算法、计时或诊断技术变化 |
| Adapters | 任务格式、case 选择、reference、规则、默认值、profile、评分与任务报告 | benchmark 或任务语义变化 |

**Ascend 是部署和资源领域；Triton、AscendC 是实现技术；CANNBench 是任务与规则来源。**
产品名选择 Ascend Op Eval，因为后两者可以变化，而运行于 Ascend 并产生算子评测证据是项目的稳定用途。
CPU 构建和控制任务仍属于这个用途。

设计由以下不变量约束：

- 准入在执行前持久化身份；重试和恢复保留原 owner 与冻结的要求。
- 一项逻辑执行可以有多个 attempt；只有合法租约持有者能够发布对应结果。
- 程序结束、产物齐全、比较通过、任务达标分别表达；不存在覆盖全部含义的 `success`。
- 参数化通用方法属于服务能力；benchmark 的默认值、门槛、评分属于外部 adapter。
- 自定义方法和 candidate 的代码都按其权限在 worker 运行；声明来自调用方的方法不自动成为服务认证的裁判。
- adapter 独立维护和发行；它打包的程序仍可在 worker 上运行。
- 方法调用与普通程序执行复用一个持久化执行生命周期。六项能力不要求六个 HTTP 请求。

该方向延续[六项通用能力](../execution-core/capabilities.md)和[执行核心设计](../execution-core/README.md)。
相对现有 spec 的主要调整是：**内部包名也纳入最终更名目标**，通过分阶段兼容完成，不永久保留 Triton 品牌的主 namespace。

## 3. 统一领域语言

完整的候选词汇见 [GLOSSARY.md](GLOSSARY.md)。本目录内的术语表是评审草案，接受后才提升为根目录的正式词汇表。

| 术语 | 使用位置与约束 |
| --- | --- |
| Operator / 算子 | 讨论任务的计算行为；`op` 只用于已确定的项目名或既有工具标识 |
| Candidate / 候选实现 | 待评估实现，可能是 Triton、AscendC、Python 或原生可执行工程 |
| Reference / 参考实现 | 任务指定的比较依据；不默认等同于 Torch 或 CPU |
| Workload / 工作负载 | 一组待执行输入与属性的描述；保留外部格式中的既有拼写 |
| Case / 执行样例 | workload 在确定配置下解析成的一次具体输入场景 |
| Evaluation / 评测 | adapter 组织和解释的一项任务，可关联多个 execution |
| Execution / 执行 | 服务受理、具有稳定身份并可恢复的一项执行请求 |
| Attempt / 执行尝试 | execution 的某次受租约约束的实际运行 |
| Method / 方法 | 有身份、参数和结果契约的可复用评测过程 |
| Evaluation profile / 评测配置 | adapter 的版本化规则与配置组合 |
| Profiling / 性能剖析 | profiler 采集过程；与 evaluation profile 分开描述 |
| Artifact / 产物 | 有摘要、归属、保留期的材料或结果 |
| Runtime / 运行环境 | 可匹配并记录身份的程序运行环境 |

命名由上述语义决定：不用 `run/job/task/eval` 轮流表示同一个 durable resource；底层统一使用 `execution_id`。
adapter 可以有 `evaluation_id`，但必须同时记录其所属 adapter；旧接口中的 `evaluation_id` 保留原有含义。
两者的映射显式保存，不能仅换一个字段名。

`profile` 单独出现时容易歧义：CLI 的 `profile` 动词表示性能剖析，选择规则使用 `--evaluation-profile`。
新模型分别使用 `evaluation_profile` 与 `profiling`，兼容入口继续接受既有字段。

## 4. 全仓命名契约

### 4.1 项目与发行名称

| 对象 | 目标名称 | 规则 |
| --- | --- | --- |
| 产品展示名 | `Ascend Op Eval` | README 标题、HTTP 文档标题、发布说明统一 |
| Git 仓库 slug | `ascend-op-eval` | 不再引入 `ascend-op-evaluation` 等变体 |
| 服务发行包 | `ascend-op-eval` | 承载 HTTP 控制与执行管理 |
| 服务 Python import | `ascend_op_eval` | 主命名空间完整更名 |
| SDK/CLI 发行包 | `ascend-op-eval-client` | 轻量客户端，无服务端依赖 |
| SDK import | `ascend_op_eval_client` | 显式区分客户端和服务实现 |
| 兼容 gateway 包/import | `ascend-op-eval-compat` / `ascend_op_eval_compat` | 只承载列明的旧 interface；旧 import wrapper 另按实际消费者需要提供 |
| 用户 CLI | `ascend-op-eval` | 由 client 包提供，产品入口不缩写成 `aoe` |
| 服务管理 CLI | `ascend-op-eval-server` | 由服务包提供，不与客户端争用 executable |
| 默认 adapter 包/import | `ascend-op-eval-adapter-default` / `ascend_op_eval_adapter_default` | 接续 definition/workloads 体验，覆盖适用的 Triton 与 native 路径 |
| CANNBench adapter 包/import | `ascend-op-eval-adapter-cannbench` / `ascend_op_eval_adapter_cannbench` | 独立发行；固定上游范围，不作为服务安装依赖 |
| 主 agent 插件/skill | `ascend-op-eval` | manifests、skill 目录与说明一致 |
| adapter 设计插件 | `ascend-op-eval-adapter-kit` | 原 `eval-adapter-kit` 的正式归属 |
| 新镜像 basename | `ascend-op-eval` | registry/组织由实际发布配置指定，部署固定 digest |
| 新部署的 Compose project / 服务名 | `ascend-op-eval` / `api`、`worker`、`redis` | project 显式配置；只有可独立部署时才拆为对应进程服务 |
| 新安装的配置/数据目录 | `/etc/ascend-op-eval/`、`/var/lib/ascend-op-eval/` | 新默认值；已有部署路径显式保留 |

这些名称是目标约定，不表示软件包名或仓库名已在远程注册。
Git owner 保留现有归属；远程 URL 在实际更名后统一更新，历史 commit permalink 保留其历史定位。
旧名称在兼容入口、历史记录、上游来源及许可证中的出现均有合法用途，不以全仓零匹配作为验收。

### 4.2 文件、符号与配置

| 类别 | 规则 | 示例 |
| --- | --- | --- |
| 文档、产品目录 | 小写 kebab-case，按主题命名 | `execution-lifecycle.md`、`native-projects.md` |
| Python 模块、函数、字段 | snake_case，使用领域名词 | `execution_store.py`、`submit_execution()` |
| Python 类型 | PascalCase，表达含义 | `ExecutionSpec`、`MethodDescriptor`、`ComparisonResult` |
| 部署脚本 | shell 使用 kebab-case；可导入 Python 模块使用 snake_case | `deploy-host.sh`、`release_manifest.py` |
| 分支 | `feat/`、`fix/`、`docs/` 加具体主题 | `docs/ascend-op-eval-structure` |
| 服务端环境变量 | `ASCEND_OP_EVAL_*` | `ASCEND_OP_EVAL_REDIS_URL` |
| 客户端环境变量 | `ASCEND_OP_EVAL_CLIENT_*` | `ASCEND_OP_EVAL_CLIENT_URL`、`ASCEND_OP_EVAL_CLIENT_CAPABILITY_FILE` |
| 上游工具变量 | 保留上游名称 | `CANN_SET_ENV_PATH`、`MSPROF_BIN` |
| method 标识 | `namespace.method-name`，版本/摘要单独记录 | `builtin.allclose` + version + digest |
| 错误码 | 稳定 snake_case，归属明确 | `runtime_unavailable`、`method_protocol_error` |
| 指标与日志 | 新指标前缀 `ascend_op_eval_`；日志含 execution/attempt 身份 | 物理卡身份和 attempt 一起记录 |

不在字段名里重复全部项目名。禁止增加含糊的顶层 `utils/common/manager/engine` 作为新职责的收纳目录。
`engine` 对现有有来源的代码仍可作为迁移期间的历史名称。
`AOE-xx` 作为现有 ticket ID 保持稳定；不把 `aoe` 扩展成用户必须学习的另一套产品缩写。

### 4.3 版本与身份

分别记录 service release、client release、adapter release、HTTP contract、storage schema、method identity、runtime identity 和 evaluation profile identity。
包版本描述发行；契约版本描述可兼容行为；digest 描述不可变内容，三者互不替代。

独立发行包允许独立版本。插件版本与其携带的客户端构建保持一致；client 与 server 通过兼容矩阵和契约测试匹配，取消“所有发行数字必须相同”的隐含约束。
单一来源指每项身份各有一个来源，不是用同一版本号替代所有身份。
不因品牌变化重置版本或宣称 `1.0` 稳定；发布编号在契约与兼容范围确定后选择。
多包发行后采用 `<package-name>-v<version>` 的 tag 和明确的发布物名称；旧 `v*` tags 保留历史身份，release automation 同步调整解析规则。

## 5. 目标仓库：单仓开发，独立发行

推荐使用 monorepo：当前团队仍需共同修改契约、运行环境、方法和消费者，跨仓拆分会提前增加协调成本。
独立包、依赖约束和契约测试先建立可迁出的界面，后续 adapter 移仓无需改执行契约。

以下是完成迁移后的目标；目录随实际内容建立，不预建空壳：

```text
ascend-op-eval/
├── README.md
├── GLOSSARY.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── THIRD_PARTY_NOTICES.md
├── pyproject.toml                    # 仓库级工具配置，不隐式安装全部包
├── packages/
│   ├── ascend-op-eval/
│   │   ├── pyproject.toml
│   │   └── src/ascend_op_eval/
│   │       ├── api/                   # HTTP 解码、鉴权、响应
│   │       ├── control/               # 准入、持久化状态、调度、恢复
│   │       ├── execution/             # worker、进程监督、取消、结果发布
│   │       ├── resources/             # 设备、租约分配、健康管理
│   │       ├── runtimes/              # 环境匹配与隔离实现
│   │       ├── artifacts/             # 封存、访问、保留与收集
│   │       ├── methods/               # descriptor、参数及通用方法
│   │       ├── config.py
│   │       └── versioning.py
│   ├── ascend-op-eval-client/
│   │   ├── pyproject.toml
│   │   └── src/ascend_op_eval_client/ # submit/recover/events/artifacts/CLI
│   └── ascend-op-eval-compat/         # 有退出条件的兼容 gateway
├── adapters/
│   ├── default/                      # 独立 pyproject、src、tests、profiles
│   └── cannbench/                    # 同上，固定上游与独立一致性验收
├── plugins/
│   ├── ascend-op-eval/               # manifests、skill、可移植客户端入口
│   └── ascend-op-eval-adapter-kit/   # 方法映射、模板与验收指导
├── deploy/
│   ├── compose/                      # compose.yaml、env 示例、启动 wrapper
│   ├── host/                         # 宿主部署配置和启动入口
│   └── images/                       # 控制服务与 worker runtime 的构建材料
├── scripts/                          # 仓库维护、发布和验收编排
├── examples/                         # CPU、Triton、AscendC、自定义方法完整路径
├── tests/
│   ├── contract/                     # 包/HTTP/消费者兼容
│   ├── integration/                  # 持久化、隔离、恢复、取消
│   ├── npu/                          # 真实硬件验收
│   └── fixtures/                     # 保留来源及相应许可证
└── docs/                             # 见文档体系
```

各包的局部测试放包内 `tests/`；根 `tests/` 负责跨包验收。迁移测试位置时保留原测试意图，后续再消除重复。
开发安装以明确的 `pip install -e <package-path>` 等包级命令为基础，不强制换包管理器。
各包独立构建 wheel，检查 wheel 中的资源、模板和许可证齐全。

### 5.1 依赖必须与发行边界一致

```text
agent plugin → client CLI/SDK → 服务的 HTTP interface
外部 adapter → client SDK + 自身任务依赖
HTTP → control → execution → runtimes / resources / artifacts
                              └→ methods 的执行程序
compat → 旧协议解码/恢复 + 新契约客户端
```

- 服务包不导入 adapter、benchmark profile 或 CLI 包。
- control 不导入 Torch、Triton、CANNBench；方法描述和准入校验不导入用户代码。
- Torch/NPU/compiler/profiler 等执行依赖归匹配的 worker runtime；HTTP/control 的基础安装保持轻量。
- 方法实现可在 `methods/` 提供，重依赖仅在对应运行环境执行时加载；新增独立 method 包要有实际发行需要。
- client 不导入服务源码，通过公开 interface 验证，不读取 Redis。
- 默认 adapter 支持的实现类型由其规则和 runtime capabilities 决定，服务核心不增加候选语言枚举分支。
- `contracts/` 仅在有可复用内容时建立；HTTP schema 从实现生成并做兼容验证，不恢复旧的手写平行 schema 或 startup schema-file gate。

### 5.2 当前代码如何归位

| 当前位置 | 目标归属 | 必须完成的语义整理 |
| --- | --- | --- |
| `api/` | `api/` | 传输层保持轻薄；旧格式从新执行契约中分离 |
| `service/instance.py`、`admission.py`、`broker.py`、`models.py` | `control/` | 保留状态机和 fencing，拆出旧 check/grade 特有模型 |
| `runtime/worker.py` | `execution/` | worker 使用冻结的执行要求，复用已有恢复原则 |
| `runtime/health.py`、card/lease 逻辑 | `resources/` | 设备健康与 candidate 正确性分离 |
| `runtimes/sandbox.py`、`execution_environment.py` | `runtimes/` | 环境、隔离与清理归同一明确职责 |
| `evaluators/base.py` | `execution/`、`artifacts/` | 拆出进程监督和结果收集，消除对两段 Python 源码的假设 |
| `operator_input.py`、`evaluators/evaluation.py` | 默认 adapter | 输入协议、case 选择和检查编排归任务 |
| `engine/` 中可复用的生成/比较/测量/诊断实现 | `methods/` 或相应运行程序 | 方法有明确参数与证据；保留第三方来源，先迁移后有依据地修正 |
| `engine/` 中任务默认值、grade 与专用 harness | 默认 adapter 的私有实现 | 与严格规则、legacy 规则分别标识，不把历史缺陷当标准 |
| `runtime/*cache*`、`reference_timing_reuse.py` | adapter 的策略 + 核心 artifact 存储 | 缓存身份、判定/时延复用规则归 adapter；核心处理摘要、访问与保留 |
| `runtime/correctness_evidence.py`、`service/terminal_results.py` | adapter/method 结果解释 + `execution/` 事实发布 | 按实际函数拆分，保留唯一 fenced 终态发布路径 |
| `serialization.py`、`versioning.py` | 相应服务/客户端包的必要 interface | 不创建互相依赖的“共享万能包” |
| `scripts/run_api.py`、`run_worker.py` | 服务安装后的 CLI | 仓库脚本可暂作薄 wrapper，部署不依赖源码 cwd |

通用方法按职责提供 `prepare/build/execute/compare/measure/diagnose`，允许组合和按需跳过。
公共操作保持少量：发现能力、封存材料、提交、读取、取消和获取产物；把复杂监督行为收在 implementation 内部。
不为了对称把每个职责拆成独立进程或独立发行包。

## 6. 文档从目录搬迁变成知识归属重构

### 6.1 新导航与唯一来源

```text
docs/
├── README.md                         # 按读者任务导航，并显示 current/proposed
├── guides/                           # 调用者：首次评测、native、自定义方法、恢复
├── reference/                        # 参数、CLI、配置、方法协议、能力与兼容矩阵
├── explanation/                      # 已实现的领域关系、生命周期、证据与隔离
├── operations/                       # 部署、升级、设备健康、监控、故障处理
├── development/                      # 本地开发、包依赖、测试、发布、agent 协作
├── adr/                              # 稳定编号的已决策记录
├── proposals/                        # 尚未实现或待决策的完整方案
├── research/                         # 外部源码审查、实验分析与证据
├── plans/                            # 当前 spec、tickets、依赖与实施证据入口
└── migration/                        # 命名/契约/数据迁移与旧版本使用说明
```

按维护责任去重：参数约束归 reference；可运行步骤归 guide；机制原因归 explanation；部署动作归 operations。
其他页面链接到唯一来源，不复制完整参数表或再维护第二套安装步骤。
`README.md` 只保留定位、实际支持范围、一条完整 quick start、入口导航和贡献入口；词汇移到 GLOSSARY，贡献细则移到 CONTRIBUTING。

### 6.2 每页明确“现在、计划、历史”

规范性文档采用简短元数据：

```yaml
---
status: current
applies_to: legacy-evaluation
verified_revision: <实际核对过的 revision>
owner: <维护该主题的角色或团队>
---
```

`status` 只使用 `current/proposed/deprecated/historical`。`applies_to` 使用实际契约或包范围；目标尚未落地时不得冒充已发布版本。
`verified_revision` 表示内容核对基线，不表示完成了 NPU 验收；验证结论单列证据范围。
研究页增加来源固定版本、研究日期、已验证/未验证范围。proposed 页面必须醒目标出示例不可直接用于当前服务。
ADR 保留 accepted/superseded 等原有决策状态和编号，不机械套成实施状态。

支持矩阵把“实现”和“验证”拆开：

| 能力 | implementation | validation | 证据范围 |
| --- | --- | --- | --- |
| 某项能力 | planned / implemented / deprecated | unverified / cpu / npu / upstream-parity | revision、runtime、设备、命令和报告 |

该表由实际证据填写。`cpu` 不推出 `npu`；固定公开快照的一致性不推出线上隐藏任务一致性。

维护策略：文件路径、符号和参数使用英文；正式用户与运维文档优先保持现有英文主线。
设计讨论和研究材料允许中文；一主题只维护一个规范正文，暂不引入全站中英双份翻译负担。

### 6.3 当前文档的迁移清单

下列目标均为计划路径；原文按段落重新归属，不能只改目录名并保留相互矛盾的内容。

| 当前材料 | 处理与目标 |
| --- | --- |
| 根 README、`docs/README.md` | 重写产品定位与导航，保留当前可执行 quick start；目标示例留在 proposals |
| README 的 Domain vocabulary | 接受词汇后提升至根 `GLOSSARY.md`；旧术语解释归 migration |
| `usage/evaluations.md` | 通用操作拆到 `guides/`；字段拆到 `reference/`；legacy 协议完整用法进入 `migration/legacy-evaluations.md` |
| `usage/kernel-eval.md` | `guides/evaluate-an-operator.md`；verify/benchmark/profile 的当前语义明确归 adapter |
| `usage/native-candidates.md` | 当前 native 格式归 migration，新公开接口落地后写 `guides/native-projects.md` |
| `architecture/kernel-evaluation.md` | 当前链路进入 migration；新链路经实现核对后写 `explanation/execution-lifecycle.md` |
| `architecture/execution-core-design.md`、`generic-evaluation-capabilities.md` | 组成一份执行与方法的 canonical proposal；消除“后续修订覆盖前文”的阅读依赖 |
| `architecture/ascendc-support-assessment.md` | `research/ascendc-support-assessment.md`；过时的范围和工期判断标记历史 |
| `architecture/ascendc-evaluation-methods-review.md` | `research/cannbench-methods-review.md`，按实际审查对象命名 |
| `architecture/cannbot-methods-review.md` | `research/cannbot-methods-review.md`；来源名称保持原样 |
| `architecture/verifier-first-principles-audit.md` | `research/verifier-audit.md`；缺陷、复现、修复版本和未验证项分清 |
| `architecture/card-health.md` | 原理归 `explanation/device-health.md`；操作归 operations |
| `architecture/attempt-card-provenance.md` | `explanation/execution-provenance.md`，保留 attempt 与物理设备关系 |
| `architecture/engine-sandbox.md` | `explanation/execution-isolation.md`；当前实现限制留在适用范围内 |
| `architecture/profile-evidence.md` | `explanation/measurement-evidence.md`；任务规则归 adapter 文档 |
| `architecture/reference-device-policy.md` | 默认 adapter reference；部署特定规则归对应 operations 页面 |
| `architecture/candidate-input-defaults.md` 及其 evidence JSON | legacy adapter 的兼容说明与 fixture provenance；保留证据链接 |
| `operations/deployment.md` | 拆为控制服务部署与 worker runtime 准备，统一新入口并链接旧部署迁移 |
| `operations/recovery.md` | 当前恢复与升级保持可用；品牌切换另设 `migration/rename-and-cutover.md` |
| `operations/versioning.md` | `reference/release-identity.md` + `development/releases.md`，分别描述身份与发布动作 |
| `operations/process-labels.md` | operations 中保留；通用标签用 execution/attempt，Trit/AscC 仅为程序声明的展示信息 |
| `operations/profiler-runtime.md` | worker runtime 准备指南；旧 source-pin 路径留在迁移说明 |
| `operations/reference-cache.md` | 默认 adapter 的策略 reference + 对应运维步骤，保留每类复用证据范围 |
| `operations/npu-validation.md` | 可运行门禁归 `development/npu-validation.md`；未实现的全量矩阵归 plans |
| `operations/feedback-performance.md` | 可重复实验步骤归 development；测量结论与原始证据归 research |
| `operations/benchmark-pipe-utilization-handoff.md` | 当前交接归 plans；已完成结论转 research 后从常规运维导航退出 |
| `adr/0001-*`、`adr/0002-*` | 编号和历史决定保留；新决定通过后续 ADR 补充或显式 supersede |
| `.scratch/ascend-op-eval/` 的 spec、issues、graph、prompts | 提升至 `plans/ascend-op-eval/`，保持 AOE IDs 和依赖；移动时修正相对路径 |
| `.scratch/ascend-op-eval/custom-methods-*` | 提升到 plans 下独立 custom-methods 工作流；先核对与 AOE 的关系再交叉引用，不直接合并状态 |
| `docs/development/agent-workflow.md` | `development/agent-workflow.md`；tracker 入口改为正式计划路径 |
| `plans/version-system-tickets.json`、`evaluation-efficiency-tickets.json` | 分别核对活动/完成/被替代状态；保留原 ID 与来源，不再复制到另一张活动任务表 |
| `history.md` | `migration/history.md`；继续保留固定 commit 的来源定位 |
| `scripts/README.md`、`tests/README.md` | 保留就地导航，权威命令与测试说明归 development/reference 并链接 |
| 两个插件的 README、SKILL 和 references | 随插件名更新入口与归属，设计 skill 与调用 skill 共享术语；不把设计能力描述成已部署能力 |

正式计划从 `.scratch/` 提升时采用移动和路径修正，避免保留两份可变正文。
ticket 文件继续是状态和验收的唯一来源，graph 只保存依赖索引，保留原状态枚举。
scratch 中真正临时的输出仍为临时材料；不能将整个目录作为新文档站点长期维护。

## 7. 用户入口与契约如何收敛

以下仅展示目标命名，选项细节由实现对应的契约评审确定：

```text
ascend-op-eval capabilities
ascend-op-eval executions submit|get|cancel|events
ascend-op-eval artifacts upload|download
ascend-op-eval verify|benchmark|profile --adapter <name> --evaluation-profile <name> ...
ascend-op-eval-server api|worker ...
```

底层命令直接使用执行 interface。高层命令由所选择的独立 adapter 解释任务，未安装 adapter 时明确提示缺失依赖。
正式教程只在端到端路径已经实现后使用这些命令；现有 `triton_eval.py` 使用说明在兼容文档中保持可运行。
agent 插件调用同一客户端 implementation；若保留 stdlib 单文件分发，使用可追溯打包输出并验证与 client 的行为一致，避免手写第二套重试/恢复逻辑。
单文件的目标名为 `ascend_op_eval.py`，插件中仅保留打包产物入口，不从仓库相对路径 import 服务源码。

HTTP 资源建议保留 `/executions`、`/artifacts`、`/runtimes`、`/capabilities` 等领域命名。
目标执行契约与旧 `/evaluations` 明确区分，具体版本表达集中在契约规范中。
旧 `/verify`、`/benchmark`、`/profile` 作为兼容 interface 管理，不在一次更名中改变请求含义。
历史 handle 包含的 owner、URL、ID 和契约身份保持有效；新客户端必须能够识别并发往原 owner。

## 8. 兼容和数据迁移是独立设计

### 8.1 把三种变化拆开验收

| 变化 | 可以立即做的事 | 必须独立验证的事 |
| --- | --- | --- |
| 展示名称 | 文案、导航、新默认命名、issue 模板 | 远程仓库与插件安装定位 |
| 源码/安装结构 | namespace、src layout、包与 CLI | wheel 资源、imports、entrypoints、发布工具与消费者 |
| 持久化/契约 | 声明新执行身份与独立 schema | 历史恢复、幂等、owner、数据保留、升级和回退 |

名字中含旧品牌不代表内容必须迁移。例如现有 `triton-eval:v2.1` prefix 与 `triton-eval-redis-v2` volume 已有数据语义。
Compose 的 project name 还可能从 checkout 目录推导；仓库目录更名同样可能让默认 volume 定位改变。
切换前记录实际 project、volume、Redis endpoint/prefix、owner URL、release manifest 与 artifact 路径。
部署配置显式绑定旧身份；新安装才能采用新默认名称。

### 8.2 环境变量与入口兼容

- 服务旧前缀 `TRITON_EVAL_*` 只为仍有相同语义的字段提供映射；移到 adapter 的策略字段在服务中明确拒绝并给出迁移说明。
- 客户端 `EVALUATION_URL`、`EVALUATION_CAPABILITY_FILE` 映射到新的 client 前缀。
- 配置在解析时保留“是否提供”；false、0、null 和缺失不混同。
- 新旧同义变量同时存在且解析值不同，启动/调用失败并指出冲突字段；不静默选一边。相同时接受并提示弃用。
- CLI 保留旧入口 wrapper 的兼容期；仅转发具有等价语义的参数。旧插件安装名有单独迁移说明。
- 旧 Python namespace 若存在真实消费者，提供薄兼容包并测试其明确列出的公开 imports；不承诺全部内部模块路径兼容。

### 8.3 数据、缓存与身份

新执行记录使用独立 schema/namespace，新安装可用 `ascend-op-eval:execution-v1` 这一候选命名；只有 schema 实现并验收后才能写入。
旧 `evaluation` 数据继续由旧 decoder 和 owner 读取，兼容 gateway 不给旧结果补造 execution、method 或 runtime 证据。
新旧执行格式可以隔离存放在同一受控持久化设施中，但不能通过双写建立两套互相竞争的任务状态机。

包路径变化会影响当前源码摘要、release manifest、sandbox/runtime source pins 和相关缓存身份。
所有引用都应重新生成和验证；不能把路径替换后得到的新摘要当作旧测量证据的延续。
当前缓存按其原策略保留，新 adapter 在完整身份已证明前不复用旧判定/时延。
当前第三方头部、输入生成许可证和 fixture attribution 随代码移动保留；`THIRD_PARTY_NOTICES.md` 聚合来源，不替代许可证正文。
现有缺失的 CANN 许可证正文列为发行核对项，不能通过改名消除来源义务。

兼容层的退出条件由证据决定：调用方已迁移、历史恢复承诺与保留窗口满足、旧入口使用已核对、回退演练通过，并在发布说明中给出实际移除版本。
不以“下一个 release 应该可以”作为自动删除旧入口和数据的依据。

## 9. 实施顺序与交付门槛

总体目标允许彻底重构；落地以可审查、可回退的变更集推进。
纯移动、命名兼容和评测行为变化分别提交；新正确性方法和测量规则沿已有功能计划验证。

| 阶段 | 具体交付 | 验收条件 |
| --- | --- | --- |
| P0：冻结语言与迁移清单 | 本 proposal 定稿、GLOSSARY、逐项 old→new 清单，登记实际持久化身份与外部消费者 | 每个命名面都有归属、兼容策略、验证位置；标明与现有 AOE/CM 工作重叠 |
| P1：整理知识与正式计划 | 文档状态/导航、proposal/research 分流、计划提升、相对链接修正 | 当前教程仍可执行，计划只有一个状态来源，proposed 不出现在 current 能力清单 |
| P2：建立可安装包 | 服务/client 包、src layout、目标 import 与兼容入口、wheel 资源、发布身份工具 | 安装后脱离仓库 cwd 可运行，公开 imports 与 CLI 可用；基础服务无 adapter 重依赖 |
| P3：完成职责迁移 | 通用执行与方法、外部 default/CANNBench adapter、兼容 gateway | 两类真实任务共用执行 interface；完整旧行为回归与新语义验收分别通过 |
| P4：部署和命名切换 | Docker/host 配置、CI 名称、manifests、仓库与插件定位、配置别名、升级回退手册 | 历史 handle 可恢复、volume/prefix 不变或有独立迁移证据，重建 source pins，旧新路径演练 |
| P5：移除已结束兼容 | 删除确认无消费者的 alias/wrapper，收敛 current 文档 | 满足声明的退出条件；不删除尚需恢复的状态和来源记录 |

P1 可先完成；P2/P3 按当前实现与契约依赖推进，不为完成目录图而提前做空架构。
每一阶段的必要修改覆盖根/包 pyproject、安装路径、测试 imports、fixture 路径、Docker COPY/WORKDIR、shell cwd、CI、发布 manifest、插件所有格式的 manifests，以及文档链接。
已有 source-pin 校验使这些路径成为运行身份的一部分，必须纳入变更验证。
CI workflow 按职责命名，如 `cpu-validation.yml`，不把已过时的协议代号写进常驻 workflow 名。
更改 required-check 显示名时同步核对 branch protection；远程设置未切换前保留其匹配名称，避免阻断合并。

### 9.1 与现有实施计划的关系

本提案是已有 AOE 功能计划的仓库与知识体系补充，不建立第二套功能开发状态。

- AOE-01～08：沿现有路径保留执行与恢复底座，按目标 package 职责逐步归位。
- AOE-09～13、18：client、通用方法、default/CANNBench adapter 的依赖和名称以本提案统一。
- AOE-19：兼容 gateway 同时覆盖命名入口、旧契约和历史 owner 恢复。
- AOE-20：独立安装与启动验收扩展到目标 namespace、独立 wheel、CLI、manifest 和安装资源。
- AOE-21～24：加入重命名验收、兼容矩阵、source-pin 更新、文档与部署回退证据。
- custom-methods 计划保留其原范围和状态；若与 AOE 方法接口交叉，先建立字段/身份映射，再决定复用或替代，不能默认已经实施。

独立记录的文档整理工作在正式 tracker 中关联以上票据，不重编号，不宣称已有功能验收被文档迁移满足。

### 9.2 完成标准

| 验证面 | 必须能证明的结果 |
| --- | --- |
| 命名 | 当前入口统一品牌；旧名只在明确记录的兼容、历史和上游位置出现 |
| 包与依赖 | 从 wheel 安装的 server/client/adapter 独立可用；核心不 import benchmark 或 client；CPU 控制安装不要求 NPU 栈 |
| 执行行为 | 幂等、期限、取消、worker 故障、lease fencing、事件与产物恢复经过公开 interface 验证 |
| 旧消费者 | 原 CLI/HTTP 和列明的 import 仍按兼容矩阵工作；冲突配置明确失败 |
| 数据与升级 | 切换前后读取同一历史 owner 的结果；恢复窗口和保留期成立；回退不读入不支持的新格式 |
| 真实设备 | 目标 runtime 上验证 Triton、AscendC、比较、计时、profiling；只声明实际通过的范围 |
| adapter 一致性 | CANNBench 对固定公开上游做独立差分，原始输出、有效参数、失败分类与性能统计有依据 |
| 文档 | 当前命令可执行；内部链接有效；规范主题只有一份当前正文；新读者能区分已实现和提议 |
| 发行 | CI、release automation、插件包、镜像和源码身份同步；source pins 更新；第三方来源完整 |

命名扫描覆盖源码、隐藏 manifests、CI、shell、env 示例、JSON、文档和测试，并维护有理由的旧名保留清单。
通过 CPU 或字符串扫描不能替代设备行为与数据恢复验收。

## 10. 取舍与本 proposal 推荐的决定

| 选择 | 收益 | 代价与处理 |
| --- | --- | --- |
| 目标统一 `ascend-op-eval`，包括主 import | 后续使用和维护只学习一套项目命名 | 安装/import/manifest 联动变化，通过包级兼容阶段消化 |
| 单仓多包，adapter 独立发行 | 保持当前协作效率，同时建立真实依赖边界 | CI 与发布需识别包级影响，按契约验证而非全部锁同一版本 |
| 通用方法随服务能力提供，规则留在外部 adapter | 复用比较/测量技术，新 benchmark 不驱动核心名称分支 | 方法身份、参数、运行环境和报告权威必须显式表达 |
| 当前、提案、研究和历史分别组织 | 用户能够判断文档可执行性，研究结论不会冒充实现 | 需要逐页核对内容；迁移期间保留必要旧入口说明 |
| 最终彻底收敛，数据身份分阶段迁移 | 获得清晰目标结构，并保留任务恢复能力 | 兼容层有暂时成本，依据真实消费者和保留承诺退出 |

建议评审以这些决定和上述完成标准为单位。接受后先落实 P0/P1，再将 P2～P5 的命名与依赖要求合入现有实施 spec。
远程仓库更名、发布和生产部署作为实际切换动作另行执行；本次 proposal 不改变它们。
