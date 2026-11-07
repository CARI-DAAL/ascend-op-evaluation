# ascend-op-eval 开发 tickets

本地 tracker，一张 ticket 一个 Markdown 文件。已按用户确认的设计开票，本轮只规划，尚未执行开发。默认 triage 为 ready-for-agent；有 blocker 的票仍须等待依赖完成。

最新职责以[六项通用评测能力](../../proposals/execution-core/capabilities.md)为准；外部 adapter 设计使用项目 [eval-adapter-kit](../../../plugins/ascend-op-eval-adapter-kit/README.md)。24 票仍是实现拆分，不应据旧叙述把服务缩成裸执行器或加入 CANNBench 专属模块。

- [实施 spec](spec.md)：范围、包归属与验收约定。
- [完整设计](../../proposals/execution-core/README.md)：职责、接口、场景与迁移依据。
- [任务图索引](graph.json)：只索引依赖和文件，ticket 正文是状态与验收的单一来源。
- [多 agent 开发 prompt](implementation-prompt.md)：下一轮可以直接执行的协调指令。

## Tracker 状态

| Status | 含义 |
| --- | --- |
| ready-for-agent | 票已经写好；只有 blockers 全部 done 才可领取 |
| claimed | 主 agent 已指派 owner，正在独立 worktree 实现/集成 |
| blocked | 已就绪票遭遇明确外部阻塞，Comments 写原因、影响和解除条件 |
| done | 已合入集成分支且本票全部验收通过，Evidence 完整 |

主 agent 负责 canonical ticket 的领取、状态与集成字段，implementer 回传 evidence 草稿，避免多个分支同时重写任务状态。依赖未完成本身不是 blocked；正常留在 ready-for-agent。CPU 实现票注明真实 NPU 验收在哪张票，不能代替 22/23 的设备证据。

## Tickets

1. **[AOE-01：提取通用进程执行模块，保持现有评测行为](issues/01-preserve-legacy-runner.md)**
   - Blocked by：无。
   - 交付：现有客户端仍可完成提交、验证和结果恢复，同时进程监督与文件收集可以脱离算子检查单独使用。

2. **[AOE-02：提交并恢复一个 CPU 程序的完整执行](issues/02-cpu-execution-tracer.md)**
   - Blocked by：AOE-01。
   - 交付：调用方上传简单程序与输入，提交 execution，断开连接后仍可按原 handle 取得退出信息和输出。

3. **[AOE-03：安全传递多文件工程和大产物](issues/03-artifact-trees-retention.md)**
   - Blocked by：AOE-02。
   - 交付：调用方上传源码工程或数据集，任务能使用完整文件树；日志、动态库和报告可按摘要下载并在排队与恢复期间保留。

4. **[AOE-04：发现并严格匹配可执行环境](issues/04-runtime-capabilities.md)**
   - Blocked by：AOE-02。
   - 交付：adapter 可以查询环境能力并请求固定 runtime；环境不符时得到明确拒绝，而不是在错误环境中运行。

5. **[AOE-05：取消和资源预算约束覆盖整个进程树](issues/05-cancel-budget-cleanup.md)**
   - Blocked by：AOE-02、AOE-04。
   - 交付：用户可以取消任务；程序、编译器及脱离 session 的后代在超时或预算耗尽后被清理，资源可安全再次使用。

6. **[AOE-06：worker 故障后恢复同一逻辑执行](issues/06-durable-attempt-recovery.md)**
   - Blocked by：AOE-03、AOE-05。
   - 交付：worker 或存储短暂故障后，调用方仍能恢复原任务及各 attempt 的证据，不会读到旧 attempt 覆盖的新结果。

7. **[AOE-07：流式读取执行进度并区分报告与执行事实](issues/07-events-artifact-evidence.md)**
   - Blocked by：AOE-03、AOE-05。
   - 交付：agent 在长任务运行中读取有界日志和进度，并能区分服务观察、程序声明、缺失报告与失败收集。

8. **[AOE-08：在独占 Ascend 卡上运行任意评测程序](issues/08-single-ascend-execution.md)**
   - Blocked by：AOE-04、AOE-05。
   - 交付：同一 execution 契约可以运行 CPU 或单卡 Ascend 程序，并准确记录真实设备和逻辑设备映射。

9. **[AOE-09：外部 adapter 按固定 profile 提交和恢复执行](issues/09-external-adapter-client.md)**
   - Blocked by：AOE-03、AOE-04、AOE-06、AOE-07。
   - 交付：独立于服务安装的 adapter 客户端可以将 profile 解析成执行请求，上传材料、提交、恢复并读取报告。

10. **[AOE-10：将现有 Triton 评测作为独立 adapter 运行](issues/10-external-triton-adapter.md)**
   - Blocked by：AOE-08、AOE-09。
   - 交付：用户继续使用现有 definition/workloads 和验证、计时、profiling 意图，但业务逻辑由独立默认 adapter 提供。

11. **[AOE-11：原生 AscendC 工程经相同执行契约构建和运行](issues/11-native-ascendc-program.md)**
   - Blocked by：AOE-08、AOE-09。
   - 交付：用户提交多文件 AscendC 工程和外部执行程序，获得编译日志、动态库或可执行文件及运行报告。

12. **[AOE-12：通用比较能力严格验证输出契约与输入状态](issues/12-strict-default-verification.md)**
   - Blocked by：AOE-10。
   - 交付：默认 adapter 不再因输出结构错误、dtype 改变、索引偏移或候选污染输入而接受错误实现。

13. **[AOE-13：外部 CANNBench adapter 运行固定上游快照](issues/13-external-cannbench-profile.md)**
   - Blocked by：AOE-08、AOE-09。
   - 交付：agent 选择外部 CANNBench profile，即可运行固定上游 harness 并获取原始报告及解析结果。

14. **[AOE-14：CPU 构建产物可传给独立 NPU 执行](issues/14-build-artifact-handoff.md)**
   - Blocked by：AOE-11。
   - 交付：外部 adapter 可先在 CPU runtime 构建，再把封存产物交给另一 NPU execution，无需占卡等待编译。

15. **[AOE-15：评测 controller 可启动受控隔离子执行](issues/15-isolated-child-execution.md)**
   - Blocked by：AOE-03、AOE-04、AOE-05、AOE-06。
   - 交付：外部裁判能在同一 attempt 中启动隔离候选，等待或取消并封存输出，而不把服务管理权限交给候选。

16. **[AOE-16：同一设备租约内隔离 reference 与候选状态](issues/16-isolated-device-judging.md)**
   - Blocked by：AOE-08、AOE-12、AOE-15。
   - 交付：adapter 可保持裁判和 golden 私有，在同一预留设备上依次运行独立状态的 reference/candidate，并判断输出与副作用。

17. **[AOE-17：原子预留同机多卡并运行多 rank 程序](issues/17-single-host-device-groups.md)**
   - Blocked by：AOE-06、AOE-08。
   - 交付：通信算子和多 rank 程序可以申请完整设备组，只有全部资源到位后启动，失败后整组清理。

18. **[AOE-18：外部程序在声明环境中完成计时与 profiler 导出](issues/18-measurement-profiler-programs.md)**
   - Blocked by：AOE-10、AOE-11。
   - 交付：默认及原生 adapter 可选择自己的计时窗口和 profiler，得到原始 trace、测量定义与可追溯结果。

19. **[AOE-19：旧客户端继续提交并恢复历史任务](issues/19-legacy-compatibility-gateway.md)**
   - Blocked by：AOE-06、AOE-10、AOE-12。
   - 交付：旧调用方通过独立兼容入口继续工作，历史 evaluation 按原 owner 恢复，新 execution 不被伪装成历史证据。

20. **[AOE-20：以 ascend-op-eval 独立安装和启动通用核心](issues/20-service-package-separation.md)**
   - Blocked by：AOE-13、AOE-19。
   - 交付：运维可独立安装 ascend-op-eval 控制与执行服务，选择外部 runtime；adapter 和 benchmark 更新无需服务发版。

21. **[AOE-21：完整 CPU 集成与故障恢复验收](issues/21-cpu-integration-gate.md)**
   - Blocked by：AOE-07、AOE-14、AOE-16、AOE-17、AOE-18、AOE-20。
   - 交付：所有实现汇入后，通用核心和外部 adapters 在公开接口上通过统一故障与兼容验收，形成可供设备验证的构建。

22. **[AOE-22：目标 NPU 验收执行、隔离、多卡与计时](issues/22-npu-execution-release-gate.md)**
   - Blocked by：AOE-21。
   - 交付：在目标 Ascend 环境证明单卡、原生构建、隔离子执行、多卡和 profiler 的实际能力，明确发布可支持范围。

23. **[AOE-23：验收外部 CANNBench profile 与固定上游的一致性](issues/23-cannbench-parity-gate.md)**
   - Blocked by：AOE-13、AOE-22。
   - 交付：agent 可以知道 cannbench-a3-2.0 profile 对齐了哪个具体上游快照，以及正确性、失败和性能结果的验证范围。

24. **[AOE-24：完成集成审查与可恢复的发布交付](issues/24-release-readiness-handoff.md)**
   - Blocked by：AOE-21、AOE-22、AOE-23。
   - 交付：交付一个经审查的集成分支、完整实现/设备证据、兼容矩阵和升级回退步骤，供用户决定部署。

## 并行与集成

初始 frontier 只有 01；01 完成后做 02。02 后可并行 03 与 04；后续按真实依赖动态调度，避免把这份图误读成 01→24 的全串行清单。

- 03 的产物、04 的环境、05 的执行清理分别有完整用户路径。
- 06/07/08 在依赖满足后可并行。
- 10/11/13 是三个不同外部 adapter/原生场景，可在共用契约稳定后并行。
- 15/17 可以与外部 adapter 工作并行，但共享 runtime/调度接口变化由主 agent 协调。
- 21 是整合后的 CPU 门禁；22→23→24 是设备、上游兼容与最终交付门禁。

任务依赖表示能力前置；修改同一文件造成的临时冲突由主 agent 分配区域、冻结接口或串行集成处理，不随意伪造业务依赖。以实际模型并发上限为准，默认一个主 agent 加最多三个子 agent；实现者、merger 和 reviewer 共用这些名额。

## Evidence 与完成

每张票记录实现 commit、合入 revision、实际命令及结果、原始报告位置、未覆盖范围。只做代码实现不满足硬件门禁。遇到硬件/凭证/运行环境缺失，继续所有不依赖它的 ready tickets，再给出精确阻塞清单。

本 feature 不创建远程 issues、不关闭旧计划或父任务。旧 JSON 计划保留，不与本图合并为一个双重状态源。
