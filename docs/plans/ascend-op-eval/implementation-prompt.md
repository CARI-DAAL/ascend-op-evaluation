# 多 agent 开发 prompt

以下正文可作为新会话的完整指令。起始目录是本仓库根目录。

---

你是本项目的主开发 agent。使用 Matt 的 implement-spec 工作流，协调多个 agent 实现通用算子执行服务 ascend-op-eval。任务是实现和验证已批准的设计，不是重新提方案。

## 必读上下文与来源

先读取下列内容，后续子 agent 通过这些指针获取上下文：

1. docs/plans/ascend-op-eval/spec.md
2. docs/plans/ascend-op-eval/README.md
3. docs/plans/ascend-op-eval/graph.json
4. docs/proposals/execution-core/README.md
5. 本仓库当前适用的 AGENTS.md/CLAUDE.md（若有）、README 中的贡献规范、实例所有权及 admission ADR。

最新职责修订优先读取 docs/proposals/execution-core/capabilities.md；它将服务收敛为六项通用能力，执行核心文档保留底座细节。设计外部 adapter 时使用项目插件 plugins/ascend-op-eval-adapter-kit/skills/eval-adapter-design/SKILL.md。

本轮 issue tracker 已配置为本地 Markdown：docs/plans/ascend-op-eval/issues/，一张票一个文件。Status/Evidence 以票正文为准，graph.json 仅索引依赖。不要把旧 docs/plans JSON 计划当作本轮进度。

使用已安装的 implement-spec、tdd、code-review 技能。若会话目录未列出，先检查本机 .agents/skills；当前安装位置分别为 /home/yubaifeng/.agents/skills/implement-spec/SKILL.md、/home/yubaifeng/.agents/skills/tdd/SKILL.md、/home/yubaifeng/.agents/skills/code-review/SKILL.md。先读再执行。没有专用 Skill 工具时直接读取文件并遵循流程。

## 目标与职责

- 核心接受 Program + Inputs + Runtime + Resources + Limits + Outputs，返回执行事实和 artifacts。
- 服务还提供准备数据、构建加载、执行、比较、测量、诊断的可复用方法与参数校验；不能只交付裸远程执行器，也不能硬编码 CANNBench 字段或默认规则。
- adapter 独立开发、配置、安装和版本化。实现默认 adapter、CANNBench adapter 与兼容 gateway 时可使用同仓独立发行包；核心不依赖它们。
- CANNBench 精度、输入、计时、基线、评分及 cannbench-a3-2.0 profile 全在外部 adapter。默认 adapter 的严格规则与 CANNBench 固定上游规则分开。
- 公共服务名称使用 ascend-op-eval；历史 handle、存储、内部兼容 import 和数据保留按设计迁移。
- 完成所有 tickets 的真实验收。现有 API 的假阳性不等于正确性标准；需要设备证据的票只能在实际验证后完成。

## 启动与工作区

1. 读取 git 状态和当前 HEAD，核对计划基线与当前实现的差异。保留现有修改；尤其保留工作区中的验证器审查材料。
2. 为本轮创建或恢复单一集成分支 feat/ascend-op-eval，记录分叉点。已有同名分支先检查，沿用已有进度，不覆盖。
3. 让 spec、tickets、设计和 tracker 在所有工作树可读取。若尚未提交，按文件精确收录本 feature 的规划文档形成独立 planning commit；已有文件中混有其他工作时只收录本任务内容，或保留原工作区并使用单独上下文快照。避免把用户无关改动带入规划提交。
4. 使用独立 worktree/branch 隔离每个 implementer。不要让多个 agent 在同一 checkout 修改代码；不要用破坏性 reset 清空不匹配的工作树，创建新树或保留改动后正常同步。

## 调度与角色

你负责整体契约、任务分配、集成顺序、状态和验收，不把整项工作一次性丢给一个子 agent。

- 从 graph 和票正文计算 frontier：所有 blockers 都 done 且未领取的票才可启动。最初是 AOE-01，然后 AOE-02；之后动态并行。
- 默认最多三个子 agent 同时工作，另有你作为主 agent；以平台实际并发上限为准。implementer、merger、reviewer 共用额度，避免占满后无法集成。
- 每个 implementer 负责一张票，基于当前 integration tip 创建工作树。主 agent 先写 Owner/claimed，再发任务。
- 分发时只提供 ticket、spec、适用设计章节、integration revision、工作树和本票修改区域。数据格式或共享接口需要变更时先向主 agent 说明，由主 agent 决定兼容扩展并通知消费者。
- 子 agent 用 tdd 做一条行为路径的 red→green→refactor，测试公开接口及可观察结果；不要用测试镜像实现。先定位和运行已有相关测试。
- 完成后 implementer 同步 integration tip，解决其分支与最新接口的差异，运行受影响测试并提交 scoped commits。回传实现 commits、行为摘要、实测命令/结果、未完成项及 evidence 草稿；不能自行把 canonical ticket 标 done。
- 主 agent 验证回传结果，腾出名额交给单个 merger agent 串行合入。merger 同步必要消费者并运行集成检查，禁止同时发生两个集成写入。
- 合入且满足本票门禁后，主 agent 更新 canonical ticket 的 Evidence/Status，再释放新 frontier。共享修改区域导致冲突时调整并行安排，不删减功能或虚造验收。

## 每票完成标准

依据票正文的 Acceptance criteria 与 Completion gate，而不是“代码写完了”。实现票可以将真机验证明确交给 AOE-22/23，但这些验收票仍保持未完成。

每票 evidence 至少包括：

- 实现 commits 与实际合入 revision。
- 运行过的命令、结果与 skip 情况。
- 可恢复的原始日志/报告或 artifact 引用。
- 兼容性变化、实际支持范围和剩余限制。

程序 exit=0、报告 correct=true、CPU mocks 通过，都不能替代对应的设备或判定证据。没有匹配环境时记录能力拒绝或阻塞，不改 profile 来偷偷放宽要求。

## 验证与故障

- 按仓库实际配置运行针对性测试。集成后执行完整 CPU 门禁、契约与安装检查；不要每个子 agent 重复运行所有不相关测试。
- worker/Redis/期限/取消/GC/旧 attempt 写入的故障通过可重复测试验证；任何不可解释的成功或丢失证据必须解决。
- 设备验收使用有权限且可独占的隔离测试环境。记录真实构建、runtime、任务摘要、硬件、驱动和卡映射；不要占用已有生产任务的卡。
- 性能验收先确定噪声与统计阈值，再运行对照；保留两侧原始记录，不事后调整阈值来求通过。
- 对 CANNBench 只声明实际验证的固定快照范围。网站配置或隐藏 case 不可得时明确区分公开快照对齐与完整线上对齐。
- 外部环境阻塞时先继续其他 ready tickets，写清阻塞原因和解除条件；不能用 mock 或跳过测试关闭设备验收票。

## 最终交付

实现完成后，按 code-review 技能对集成分支相对分叉点做 Standards + Spec 两轴独立审查，指向本 spec、tickets 和当前设计。修复实质问题并重跑受影响的集成/设备门禁；将最终结果写入 AOE-24。

交付一个集成分支，包含实现、独立 adapters、24 张票的准确状态、验证证据和升级/回退 runbook。所有验收通过才宣称全部完成；若仍有外部阻塞，报告已完成范围及精确待办，不把计划整体标完成。

本轮授权开发、测试、本地分支与提交、集成和必要的隔离测试部署。生产切流、公开发布、推送远程、删除旧数据不在默认动作中。无需为了重复确认已批准的设计、ticket 粒度或正常实现选择而中断工作。

结束前保留有用 evidence，清理已合入且干净的临时 worktree；保留未合入或有修改的工作树，并注明位置。
