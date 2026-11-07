# 20: 以 ascend-op-eval 独立安装和启动通用核心

**ID:** AOE-20

**What to build:** 运维可独立安装 ascend-op-eval 控制与执行服务，选择外部 runtime；adapter 和 benchmark 更新无需服务发版。

**Blocked by:** AOE-13, AOE-19

**Status:** ready-for-agent

**Owner:** unassigned

**Integration area:** 发布与包装

**Context:** 先读本 feature 的 [spec](../spec.md) 与 [tracker 约定](../README.md)。设计是行为依据；使用当前集成代码定位实现，不依赖旧文件布局。

## Scope

收缩内部业务依赖并引入公共名称；不做全仓字符串替换或强制内部 Python import/Redis 身份改名。

## Acceptance criteria

- [ ] 服务发行与入口使用 ascend-op-eval 公共名称，旧必要 CLI/环境配置通过明确别名或迁移说明兼容。
- [ ] 核心安装/导入不要求 Torch、Triton、CANNBench 或默认 adapter；硬件运行依赖由已登记 runtime 提供。
- [ ] 默认 adapter、CANNBench adapter、compatibility gateway 是独立发行单元，依赖方向不回流到核心。
- [ ] 服务版本、execution 契约、storage、runtime、adapter/profile 身份分别可发现；只宣告已实现能力。
- [ ] 新旧部署模板保留持久化 volume、owner 和恢复窗口；实际生产部署与破坏性迁移不在此任务执行。
- [ ] 保留上游许可证与 attribution；旧内部包名若仍需兼容可保留，不以机械改名掩盖架构耦合。

## Validation

干净环境分别安装核心和各外部包，验证导入依赖、CLI、配置别名、release manifest 与临时启动；运行依赖方向检查。

**Completion gate:** CPU 包装与隔离安装验证通过。 主 agent 在合入并确认本 ticket 的门禁后标 done；与本票分离的硬件门禁不因此自动完成。

## Evidence

- Implementation commits: pending
- Integration revision: pending
- Commands and results: pending
- Artifacts / reports: pending
- Limitations / follow-up: pending

## Comments

尚未开始实现。
