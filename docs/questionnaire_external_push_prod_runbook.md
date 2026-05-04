# 问卷外推线上 Runbook

## 1. 目标

把问卷外推一期到五期能力整理成一套可直接执行的线上验收和止损手册，确保：

- 提交主流程稳定
- 外推成功/失败/跳过可查
- 单条补发和批量补发可执行
- 全局总开关可止损

## 2. 线上前置条件

上线前先确认：

1. 已执行 `python app.py init-db`
2. 后台页面可打开：
   - `/admin/questionnaires`
   - `/admin/questionnaires/external-push-logs`
   - `/admin/config/app-settings`
3. 至少准备一份开启外推的线上验收问卷
4. 已准备可联调的外部 mock 地址：
   - 200 成功地址
   - 500 失败地址
   - timeout 地址

## 3. 关键配置项

必须确认：

- `QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED`
- `QUESTIONNAIRE_EXTERNAL_PUSH_TIMEOUT_SECONDS`
- 每份问卷自己的：
  - `external_push_enabled`
  - `external_push_url`

## 4. 线上总览入口

统一从这里查看：

- 全局总览：`/admin/questionnaires/external-push-logs`
- 单问卷日志：`/admin/questionnaires/<id>/external-push-logs`
- 系统设置：`/admin/config/app-settings`

## 5. 上线 smoke 顺序

### 5.1 正常成功路径

1. 确认 `QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED=true`
2. 找一份开启外推的问卷，确认 `external_push_url` 指向 200 mock
3. 提交问卷
4. 确认前端提交成功
5. 打开全局总览页，确认最新记录为成功

### 5.2 失败 + 补发路径

1. 保持全局开关开启
2. 把问卷 `external_push_url` 指向 500 或 timeout mock
3. 提交问卷
4. 确认记录出现在“仅待补发”
5. 切回 200 mock
6. 在单问卷页或全局页执行：
   - 单条补发
   - 或批量补发
7. 确认该线程从“仅待补发”消失

### 5.3 止损路径

1. 在 `/admin/config/app-settings` 把 `QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED` 改为 `false`
2. 再提交一份已开启外推的问卷
3. 确认前端提交仍成功
4. 确认外部 mock 没有收到请求
5. 在全局页确认最新状态显示“全局关闭跳过”

## 6. 如何查看日志与待补发

全局页重点看：

- 已开启外推问卷数
- 外推日志总数
- 当前待补发
- 最近 24h 成功
- 最近 24h 失败
- 全局总开关状态

排查失败时优先使用：

- `status=failed_current`
- 问卷标题筛选
- `user_id`
- `target_url`

## 7. 如何补发

### 单条补发

1. 打开单问卷页或全局页
2. 找到当前结果为失败的线程
3. 点击“补发”
4. 查看最近结果是否变成“补发成功”

### 批量补发

1. 打开“仅待补发”
2. 勾选当前页失败线程
3. 点击“批量补发已选失败项”
4. 查看顶部汇总提示：
   - 选中多少
   - 实际补发多少
   - 成功多少
   - 失败多少
   - 跳过多少

## 8. 紧急止损口径

如果外部服务异常、误推送、需要立刻停发：

1. 到 `/admin/config/app-settings`
2. 把 `QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED` 设为 `false`

影响：

- 新的问卷提交不会再发出外推请求
- 问卷提交主流程仍成功
- 日志会留下“全局关闭跳过”

不影响：

- 问卷创建/编辑
- 问卷提交落库
- 既有日志查看
- 既有失败补发历史

## 9. 当前明确不做

- 自动重试
- 定时补发
- 鉴权/签名
- 回调
- 队列

