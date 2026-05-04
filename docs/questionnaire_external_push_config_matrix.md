# 问卷外推配置矩阵

| 配置项名 | 用途 | 是否必填 | 未配置时行为 | 是否生产必填 |
| --- | --- | --- | --- | --- |
| `QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED` | 问卷外推全局总开关；关闭时对已开启问卷记录“全局关闭跳过”并停止发请求 | 建议必填 | 未配置时默认按开启处理 | 是 |
| `QUESTIONNAIRE_EXTERNAL_PUSH_TIMEOUT_SECONDS` | 问卷外推请求超时时间（秒） | 否 | 默认 3 秒，并按 0.5~10 秒截断 | 否 |
| `questionnaires.external_push_enabled` | 单份问卷是否启用外推 | 对启用问卷必填 | 未开启时提交成功但不走外推链路 | 是 |
| `questionnaires.external_push_url` | 单份问卷外推目标地址 | 单问卷启用时必填 | 开启但为空时后台保存直接报错 | 是 |

## 说明

- 本期仍然不做：
  - 鉴权
  - 自动重试
  - 定时补发
  - 回调
  - 队列
- 成功判定仍然只看 HTTP 200。

