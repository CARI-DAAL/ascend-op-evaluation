# __NAME__ adapter 设计

## 目标

上游仓库与固定 revision：__SOURCE__。
任务/规则/数据版本、入口、硬件与验证范围：__SCOPE__。
adapter 所在独立包或项目：__LOCATION__。

## 六项能力如何组合

| 通用能力 | 本任务选择的方法与版本 | 必要参数、输入与产物 |
| --- | --- | --- |
| 准备数据 | __METHOD__ | __PARAMS__ |
| 构建加载 | __METHOD__ | __PARAMS__ |
| 执行 | __METHOD__ | __PARAMS__ |
| 比较 | __METHOD__ | __PARAMS__ |
| 测量 | __METHOD__ | __PARAMS__ |
| 诊断 | __METHOD_OR_NOT_REQUESTED__ | __PARAMS__ |

默认值/overrides 的优先级：__PRECEDENCE__。
需要提供的自定义函数或方法包：__EXTENSIONS__。
缺失的服务通用能力及可复用理由：__GAPS__。

## 参数对应表

| 上游参数及来源 | 类型/单位/默认值 | 映射能力与实际消费字段 | 转换/约束 | 生效测试 | 状态 |
| --- | --- | --- | --- | --- | --- |
| __PARAM__ | __DOMAIN__ | __TARGET__ | __RULE__ | __TEST__ | planned / implemented / verified / gap |

检查 CLI、配置、环境变量、任务 attributes、hooks 和注册接口；明确尚未覆盖项。未请求的诊断不必执行，不适用的参数说明原因。

## 语义与结果

输出结构、dtype、布局和副作用契约：__OUTPUT_CONTRACT__。
golden/reference 精度、checker、容差与特殊值：__CORRECTNESS__。
collector、同步、launch/rank 归属、conditioning 和聚合：__MEASUREMENT__。
有效配置、方法版本、环境与产物的身份记录：__IDENTITY__。
基线/评分、strict/custom profile、允许覆盖项：__PROFILE__。
错误、部分结果、缺报告、超时及恢复：__FAILURES__。

## 验收

逐参数生效测试、重要交互、正确/错解/异常样例：__TESTS__。
直接上游与服务路径差分、预先确定的性能判据：__PARITY__。
实际 CPU/设备证据与未验证范围：__EVIDENCE__。
