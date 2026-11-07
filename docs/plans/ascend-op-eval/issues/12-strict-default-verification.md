# 12: 通用比较能力严格验证输出契约与输入状态

**ID:** AOE-12

**What to build:** 默认 adapter 不再因输出结构错误、dtype 改变、索引偏移或候选污染输入而接受错误实现。

**Blocked by:** AOE-10

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 默认 adapter

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

提供可复用的比较方法与参数化输出契约，由默认 adapter 选择严格策略修复已知缺陷；不改变 CANNBench 固定快照规则，也不静默修改旧 v2.1 策略。

## Acceptance criteria

- [ ] 严格策略先校验完整输出树、叶子类型、shape、dtype 和契约声明的设备/布局，再进行数值比较。
- [ ] 索引和计数按显式输出语义严格比较，不再用浮点输入/整数输出自动推断量化容差。
- [ ] reference 与 candidate 使用独立输入状态；保留声明的内部 alias/view/inplace 语义，禁止副作用时检查后状态。
- [ ] 整数比较避免溢出，float64 等误差计算不因无声降精度消除差异；不支持 dtype 明确拒绝。
- [ ] 已有结构/dtype/索引/嵌套输入污染/数值溢出反例成为公开 adapter 接口回归，正确实现仍通过。
- [ ] 结果标明比较方法、有效精度参数、策略身份和覆盖范围，legacy 与 strict 明确区分；数值算法位于通用方法模块，执行内核不作任务判分，服务不硬编码 benchmark 默认阈值。

## Validation

使用 CPU 可重现样例测试严格比较和状态语义，经 adapter→generic execution 至少回放一组正确/错误程序；设备相关契约交给 22。

**Completion gate:** 所有已列 CPU 反例修复；此任务不证明恶意同进程候选无法篡改裁判。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
