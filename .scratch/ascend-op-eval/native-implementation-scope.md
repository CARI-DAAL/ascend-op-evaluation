# 本 session：AscendC 评测能力

实施基线：bc22bacf51a659438dd28439644cc7d96f93382b。
集成分支：feat/ascendc-evaluation。长期 24 张票不作为本轮全部完成条件。

## 用户范围

现有服务增加 AscendC 原生工程的构建、正确性与性能路径，保留 Triton 兼容性；通用机制不包含 CANNBench adapter 或榜单规则。用户已指定本机仅 CPU 验证，NPU 实测留待 server，本次提供计划与可执行驱动。

## 接入契约与选择

- public candidate(kind=native, files, build argv, module:function entrypoint, build_timeout_seconds, kernel_names, event_timing) 与 triton_code 互斥。
- 首版 source-only UTF-8 多文件工程、Python Tensor-tree 调用入口；构建在已准入的私有 attempt 内进行，保留编译诊断、期限、租约与清理。
- 比较方法 native_tensor_v1 显式校验输出结构、shape、dtype 与设备，整数/bool 精确比较，浮点使用 FP64 误差计算和参数化容差。原生方法的绝对 cap 语义与旧方法分别说明。
- 性能默认 native_profiler_kernel_sum_v1：warmup 后逐调用独立采集，累加全部 kernel launch 时长，再计算调用平均；保留原始样本，reference 同口径。
- Event 需要显式当前 stream/依赖声明。原生 op/deep 需要 kernel_names。原生 performance+trace 联合请求首版明确拒绝，支持分开请求。
- 原生 correctness reuse 与 baseline reuse 首版拒绝；构建产物完整性在检查前后验证。该机制不宣称同进程恶意候选无法篡改裁判。

## 验收

公开提交→CPU worker 真实构建→结果查询/幂等恢复、错误日志；输入与源码校验；比较器正确/错误样例与 nested alias；重复 kernel 计时样本与报告一致性；CLI 打包安全；旧 Triton CPU 回归；独立 Standards/Spec review。

server 计划覆盖实际 CANN 编译、pointwise/reduction/matrix 非对齐例、故意错解、构建/运行失败、并发隔离、退出清理与 profiler。未执行设备检查不标作已验收。

## 团队交付

- build：61d5c04，模型、转换、构建、编排与结果保存；focused CPU 322 passed。
- methods：d08fc05，原生比较和测量；focused CPU 173 passed，1 项等待集成 schema/shaping。
- client：52fbe94，CLI、样例、server gate；focused CPU 100 passed。
- 主 agent：HTTP/worker 集成测试、方法证据 shaping、全量集成与审查。

分支测试不替代最终集成结果；最终证据在实施完成时追加。

## 最终 CPU 验收

已测代码 revision：1ff5ea094bdbd34ac874fdbef82c049b773a7bef。
全量：2578 passed、13 skipped、7 deselected，116.27 秒。Ruff、compileall、diff-check 通过。
原始日志：/tmp/ascendc-release-cpu.log；结构化记录见 [native-cpu-validation.json](native-cpu-validation.json)。

Standards 审查的构建证据恢复、native provenance、文件收集竞态及空目录身份问题均修复并复查；Spec 审查的首搬运 alias 和 trace 方法身份问题均修复并复查。另修复 legacy 测试回归及官方输入默认 sentinel 的 native 复制语义。

此状态仅表示本轮实现与 CPU 验收完成，不关闭长期 24 张票。真实 CANN 编译、NPU 数值、stream、时延及 profiler 工具兼容仍以 [server 计划](../../docs/usage/native-candidates.md#device-validation) 验收；本机未运行 NPU。
