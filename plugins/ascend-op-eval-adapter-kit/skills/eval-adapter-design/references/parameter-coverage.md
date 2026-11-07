# 参数对应表：只用于查漏

对固定上游版本列清参数，不为它们建立另一套大型框架。沿用项目已有 JSON/YAML/CLI 方式配置即可。

## 每项回答六个问题

1. 参数从哪里来：CLI、config、环境变量、task attributes 或 hook？
2. 它真正影响什么：输入、构建、执行、比较、采集、聚合、资源还是展示？
3. 映射到哪个通用能力的哪个消费位置？
4. 类型/单位/默认值/优先级是否保持？尤其注意零、false、null 和未提供。
5. 什么测试证明修改它确实生效？
6. 当前是 planned、implemented、verified，还是仍有 gap？

同一 flag 在不同 subcommand 下可能有不同含义；别名归一化、路径/设备重写、废弃字段和条件生效项都要说明。task 的任意 attributes 或动态注册不能只凭静态 CLI 列表声称已全部覆盖。

## 映射位置

| 参数影响 | 去向 |
| --- | --- |
| 精度、采样、统计方式 | 通用方法的 parameters |
| 特殊生成器/golden/checker | 自定义函数或版本化方法包 |
| 数据集、源码、缓存/基线文件 | 不可变 artifact |
| 设备、进程、超时、内存 | 资源/预算请求，受父租约约束 |
| 任务选择、profile、评分、展示 | 外部 adapter |

找不到去向时，先判断是缺通用能力还是需要外部方法实现。不要在服务里加 benchmark 专属字段。

## 覆盖验收

“表里有行”不等于支持。改变参数后检查有效配置、输入、样本数、launch 归属、判定或明确拒绝是否符合预期。测重要交互，例如 strategy × level、warmup × repeat × batch、golden precision × checker、设备组 × 进程数、cache mode × case 选择。

允许合法的自定义配置，但它改变固定 profile 的规则时标 custom，不继续宣称榜单等价。任何不能实现的值或组合明确返回 gap/unsupported；不静默改值或忽略。
