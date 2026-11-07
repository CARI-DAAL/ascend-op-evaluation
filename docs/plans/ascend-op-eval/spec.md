# ascend-op-eval：通用执行核心与外部 adapter

**Status:** ready-for-agent

**Baseline:** bc22bacf51a659438dd28439644cc7d96f93382b

**Tracker:** 本目录的独立 Markdown tickets；入口见 [README](README.md)。

## Problem Statement

当前评测服务将候选语言、输入形式、检查顺序、比较与测量规则绑定在执行链路里。新任务需要反复修改服务，CANNBench 也无法仅通过外部配置忠实复用上游规则。用户已确认：服务提供通用执行能力，adapter 在服务外独立维护、配置和发布。

## Solution

最新职责以[六项通用评测能力](../../proposals/execution-core/capabilities.md)为准：准备数据、构建加载、执行、比较、测量、诊断。adapter 独立选择与组合这些能力，服务不实现 CANNBench 专属适配。设计指导见项目内 [eval-adapter-kit](../../../plugins/ascend-op-eval-adapter-kit/README.md)。

使用 Program、Inputs、Runtime、Resources、Limits、Outputs 构成执行请求，返回持久化的执行事实与产物。外部 adapter 准备并解释这些材料。名字采用 ascend-op-eval；cannbench-a3-2.0 属于外部 profile。

[完整架构设计](../../proposals/execution-core/README.md)是行为与职责的主要依据。本 spec 确定通用执行功能的实施范围和交付约定；命名与安装结构已按仓库重构 proposal 调整，不能据此将尚未验收的 AOE 功能票标 done；[AscendC 调研](../../research/ascendc-support-assessment.md)提供历史来源，不沿用其中较窄后端扩展的工期估计。

涉及正确性、计时或工具能力的 tickets，先读后续[固定 CANNBench 源码方法审查](../../research/cannbench-methods-review.md)及[skills / msprof 方法审查](../../research/cannbot-methods-review.md)。它们明确具体协议与证据边界；不同来源的采样、聚合、golden 和容差不能混用来声称上游兼容。

## User Stories

1. 作为 agent，我可以上传不同语言的多文件工程，不必包装成固定的 Python 模型。
2. 作为 adapter 作者，我可以自行定义输入生成、golden、输出状态、容差、测量与评分。
3. 作为调用方，我可以固定程序、输入和环境的字节身份，并重放同一逻辑请求。
4. 作为调用方，我可以断开连接后使用原 owner handle 恢复任务。
5. 作为调用方，我可以辨别程序结束、证据收集完成和算子正确，而不是只看一个 success。
6. 作为运维，我可以登记实际可用 runtime，并拒绝不匹配环境或权限要求。
7. 作为开发者，我可以在私有环境编译、安装和加载同名扩展而不污染其他任务。
8. 作为调用方，我可以取消、限制资源和期限，并确认后代进程已清理。
9. 作为 agent，我可以读取有界日志和进度，并明确看到输出缺失、截断或过期。
10. 作为 adapter 作者，我可以先做 CPU 构建，再通过不可变产物运行 NPU 测量。
11. 作为裁判作者，我可以让 controller 与候选处在不同隔离域，保持 golden 和最终报告私有。
12. 作为算子开发者，我可以评测复合输出、非连续布局、alias、inplace 和有状态程序。
13. 作为通信算子开发者，我可以申请同机设备组并运行多 rank 程序。
14. 作为性能开发者，我可以使用自己定义的 Event、kernel-sum 或 profiler 流程，并保留原始数据。
15. 作为旧客户端用户，我可以继续查询历史任务，在兼容入口提交旧格式请求。
16. 作为 CANNBench 用户，我可以明确知道外部 profile 对齐了哪个上游快照和验证范围。
17. 作为维护者，我可以更新 adapter/任务包而不修改核心枚举或发布服务。
18. 作为发布者，我可以检查 CPU、NPU、上游一致性和升级回退证据后再部署。

## Implementation Decisions

- 保留 durable admission、幂等、原 instance 所有权、lease/fencing 与健康恢复原则；以新契约版本引入 execution，不重新解释历史记录。
- 执行内核不导入默认 adapter、CANNBench 或业务规则；服务另提供参数化通用方法，比较/测量算法可以复用，任务默认值、门禁与分数仍归 adapter。
- 外部客户端、默认 adapter、CANNBench adapter 和兼容 gateway 采用同仓独立发行包作为开发落点；有独立依赖/测试，服务不导入它们。后续移到外部仓库不应改变执行协议。
- 第一条实现路径采用一个登记的 CPU runtime 和小型封存文件，形成真实纵向闭环；随后扩展文件树、runtime discovery 和设备能力。
- 默认 adapter 的 legacy 策略与新的严格策略显式区分。既有验证审查中的假阳性不作为正确性标准，CANNBench 则保留固定上游语义。
- 构建流程和跨 execution 产物编排属于 adapter；核心不添加业务 DAG 或自动判定/时延缓存。
- 受控子执行和同机多卡属于本轮目标能力；按 tickets 分阶段落地，在能力验收前保持未支持/未验证声明。
- 设备执行能力先用替身验证机制，再在独立硬件门禁证明真实行为。实现 ticket 的 done 只代表本票明确的门禁，不替代最终设备验收。
- 主产品、包名和 CLI 统一 ascend-op-eval，主 namespace 为 ascend_op_eval。旧 import 由可选兼容包提供；Redis prefix/volume 和历史 handle 保留其原身份。包与部署迁移见已接受的仓库重构 proposal。
- 接口、环境与存储的尚未确定字段，由首个对应 tracer ticket 给出最小可用契约和行为测试；后续修改通过主 agent 协调并同时更新消费者。

## Testing Decisions

测试从公开上传、提交、恢复、取消、日志和产物接口观察行为；内部模块用可替换 runtime/设备/时钟验证竞态。采用仓库已有的 HTTP、fakeredis、worker 失效和 sandbox 测试模式；需要时在隔离 Redis 与真实 CPU 子进程上验证持久化和清理。

- 每张 ticket 用行为测试驱动一条完整路径，不按 schema/API/worker 层分别交付空壳。
- 分支测试通过后串行集成，再运行受影响的契约与消费者测试；最终执行完整 CPU 门禁。
- 实机门禁与上游差分验收保存原始记录、实际构建摘要和预先确定的统计判据。
- 最终对集成分支进行 Standards + Spec 两轴审查，修复后重验受影响证据。

## Out of Scope

- 跨机资源协调：保留明确 unsupported，而不是模拟实现。
- 一次性支持所有厂商 NPU，或所有任意 ABI/工具链组合。
- 无证据承诺网站隐藏 case、精确线上环境或 bit-for-bit 性能一致。
- 任意宿主挂载、候选获得 Docker 管理权限、修改共享宿主 CANN。
- 自动生产部署、外部发布、破坏性数据迁移或删除历史状态。

## Further Notes

完整 ticket 图有 24 张票，每张独立、明确阻塞边。当前全部尚未实施。首次开始开发前将本 feature 文档和已确认设计固定到集成工作上下文；保留用户已有未提交工作。

[已有验证器审查](../../research/verifier-audit.md)是定位严格 adapter 反例的资料。该文件是用户工作区已有材料；本轮没有改写或重新认证其全部结论。开发者必须复现相关反例后修复。
