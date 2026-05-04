# 问卷外推上线 Checklist

## 配置检查

- [ ] `QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED` 已配置且值明确
- [ ] `QUESTIONNAIRE_EXTERNAL_PUSH_TIMEOUT_SECONDS` 已配置或确认使用默认值
- [ ] 至少一份验收问卷已开启 `external_push_enabled`
- [ ] 已开启问卷都填写了 `external_push_url`

## 总览检查

- [ ] `/admin/questionnaires/external-push-logs` 可打开
- [ ] 全局总开关状态显示正确
- [ ] 顶部能看到当前待补发数
- [ ] 顶部能看到最近 24h 成功/失败数

## 成功路径检查

- [ ] 全局开关开启
- [ ] 提交问卷成功
- [ ] 外部收到 200
- [ ] 全局页出现 success

## 失败路径检查

- [ ] 外部 500 时记录 failed
- [ ] timeout 时记录 failed
- [ ] 失败线程出现在“仅待补发”

## 补发检查

- [ ] 单条补发可用
- [ ] 批量补发可用
- [ ] 补发成功后线程不再出现在“仅待补发”
- [ ] 补发历史仍可审计

## 止损检查

- [ ] 关闭 `QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED` 后提交仍成功
- [ ] 全局关闭后不会再发外推请求
- [ ] 后台出现“全局关闭跳过”记录

## 降级口径检查

- [ ] 运维知道去哪里关闭全局总开关
- [ ] 运维知道去哪里看全局失败堆积
- [ ] 运维知道去哪里做单条/批量补发

