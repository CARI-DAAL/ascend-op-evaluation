# Eval adapter kit

项目内的 adapter 设计 skill 插件。帮助 agent 用六项通用能力描述任务，编写外部 adapter 规范、参数对应表和一致性验收方案。

- [Skill 入口](skills/eval-adapter-design/SKILL.md)
- [规范模板](skills/eval-adapter-design/assets/adapter-spec.template.md)
- [能力组合示例](skills/eval-adapter-design/assets/evaluation-plan.example.json)
- [CANNBench 参考映射](skills/eval-adapter-design/references/cannbench-reference.md)

将本目录作为完整插件交给支持的客户端注册；根 manifest 及 Codex/Claude 兼容 manifest 共用一份 skills 内容。也可直接读取 skill 文件使用。

示例请求：

> 使用 $eval-adapter-design，参考指定版本的 benchmark 和目标服务实际能力，为它设计一个外部 adapter。列出六项能力的组合、完整参数对应表、服务能力缺口和一致性验收。不要把 benchmark 专属逻辑写入服务。

插件独立于现有 triton-eval 客户端，不自动提交任务、安装全局 skill、部署服务或创建 CANNBench adapter。示例参数是设计参考，不是现有服务的可执行协议。可将本目录完整复制或打包，无需服务源码或 Python 依赖。
