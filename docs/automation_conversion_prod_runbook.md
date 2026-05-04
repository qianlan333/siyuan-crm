# 自动化转化线上总验收 Runbook

## 1. 目标

把自动化转化 1-7 能力整理成一套可执行的线上总验收顺序，确保：

- 配置齐全
- 主链路可跑
- 关键日志可查
- 风险可控
- 出问题时可快速降级

## 2. 线上部署前前置条件

上线前必须先确认：

1. 代码目录已经同步到生产目录
2. Python 依赖已经安装完成
3. `python app.py init-db` 已执行完成
4. `openclaw-wecom-postgres.service` 已重启成功
5. `/health` 返回正常
6. 后台能正常打开：
   - `/admin`
   - `/admin/questionnaires`
   - `/admin/automation-conversion`
   - `/admin/automation-conversion/programs/<program_id>/flow-design?section=sop`
7. 自动化转化问卷已经配置完成
8. 至少准备好 2 个线上验收客户：
   - 普通路径客户
   - 重点跟进路径客户

## 3. 线上必须确认的配置项

必须在线上可用：

- `AUTOMATION_INTERNAL_API_TOKEN`
- `MCP_BEARER_TOKEN`（仅 legacy 兼容需要时保留）
- `OPENCLAW_WEBHOOK_URL`
- `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TOKEN`
- `OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS`
- `AUTOMATION_ACTIVATION_WEBHOOK_TOKEN`（仅 legacy 兼容需要时保留）
- `QUESTIONNAIRE_SUBMIT_WEBHOOK_URL`
- `QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN`
- `QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS`
- `WECOM_CORP_ID`
- `WECOM_SECRET`
- `WECOM_CONTACT_SECRET`
- `WECOM_AGENT_ID`
- `WECOM_API_BASE`

如果启用自动 SOP v1，还要确认：

- `POST /api/admin/automation-conversion/sop/run-due` 已可用
- 生产调度器已经开始定时触发 `run-due`

当前第 4 块和第 5 块按真实 `owner_userid` 生效，线上总验收至少准备两个不同负责人的样本客户更稳妥。

## 4. 线上哪些 webhook 地址必须可用

至少要确认以下地址在线：

1. `OPENCLAW_WEBHOOK_URL`
   - 重点跟进池客户来消息时使用
2. `QUESTIONNAIRE_SUBMIT_WEBHOOK_URL`
   - 问卷提交成功后外发
3. `POST /api/customers/automation/activation-webhook`
   - 外部系统激活回写入口

## 5. 线上总验收执行顺序

建议顺序：

1. 健康检查
2. 配置检查
3. 问卷检查
4. 普通路径 smoke
5. 重点跟进路径 smoke
6. 异常路径 smoke
7. 日志和发送记录检查
8. 自动 SOP smoke
9. 降级/止损动作确认

## 6. 线上 smoke 检查顺序

### 普通路径 smoke

1. 提交问卷
2. 确认手机号正常保存
3. 写入 trial_opened 事实
4. 确认进入未激活普通池
5. 激活回写
6. 确认进入激活普通池
7. 验证可继续标准跟进
8. 人工确认成交
9. 确认退出营销

### 重点跟进路径 smoke

1. 提交问卷
2. 命中重点跟进
3. 写入 trial_opened 事实
4. 确认进入未激活重点跟进池
5. 客户来消息
6. 确认触发 OpenClaw webhook
7. 激活回写
8. 确认进入激活重点跟进池
9. 触发池子群发
10. 人工确认成交
11. 确认退出营销

### 异常路径 smoke

推荐优先验证：

- 沉默池不可群发

也可以补充验证：

- 问卷提交 webhook 失败但主流程不失败

### 自动 SOP smoke

1. 打开 `/admin/automation-conversion/programs/<program_id>/flow-design?section=sop`
2. 确认只出现三个池子：
   - `new_user`
   - `inactive_normal`
   - `active_normal`
3. 为每个池子确认：
   - `enabled`
   - `max_day_count`
   - `send_time`
   - `timezone`
   - day1 ~ dayN 模板
4. 至少为 `new_user day1` 配一条文本模板
5. 如需验证图片，再为 `inactive_normal day1` 配一条文本 + 图片 `image media_id` 模板
6. 用内部 token 手动触发：

```bash
curl -sS -X POST http://127.0.0.1:5001/api/admin/automation-conversion/sop/run-due \
  -H "Authorization: Bearer ${AUTOMATION_INTERNAL_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"operator":"prod_smoke"}'
```

7. 确认返回：
   - `scanned_pool_count`
   - `created_batch_count`
   - `total_success_count`
   - `total_skipped_count`
   - `total_failed_count`
   - `batch_ids`
8. 再次立即触发一次，确认同一成员同一池同一天不会重复发送
9. 再到 `/admin/automation-conversion/programs/<program_id>/flow-design?section=sop` 确认最近 batch 摘要可见

## 6.1 自动 SOP v1 业务规则

当前自动 SOP 只覆盖：

- `new_user`
- `inactive_normal`
- `active_normal`

业务规则：

- 名单执行时现算，不提前一天预生成
- 只对当前仍在对应池子的成员发
- 重复进入同池不重来，从 `last_sent_day + 1` 继续
- 离池期间错过的 day 不补发
- 当天 `send_time` 前进入池子的成员，当天可以吃到 day1
- 当天 `send_time` 后进入池子的成员，次日再吃到 day1
- SOP 和手工群发不去重
- SOP 首版只支持文本 + 图片
- 这轮不覆盖 `silent / won / focus`

## 6.2 自动 SOP schema 变更

本轮新增 5 张表：

- `automation_sop_pool_config`
- `automation_sop_template`
- `automation_sop_progress`
- `automation_sop_batch`
- `automation_sop_batch_item`

关键约束：

- `pool_key` 唯一
- `pool_key + day_index` 模板唯一
- `member_id + pool_key` 进度唯一
- `member_id + pool_key + day_index` 成功发送唯一

上线时必须执行：

```bash
python app.py init-db
```

## 6.3 自动 SOP runner 挂载方式

生产必须有调度器定时触发：

- `POST /api/admin/automation-conversion/sop/run-due`

本仓库现在正式交付了统一 due runner 脚本：

- `scripts/run_automation_conversion_due_jobs.py`

当前 registry 默认纳入：

- `sop`

保留兼容的单任务脚本：

- `scripts/run_automation_sop.py`

优先使用仓库内的 systemd timer，而不是手写 cron：

```bash
sudo cp deploy/openclaw-automation-conversion-due-runner.service /etc/systemd/system/
sudo cp deploy/openclaw-automation-conversion-due-runner.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-automation-conversion-due-runner.timer
sudo systemctl status openclaw-automation-conversion-due-runner.timer --no-pager
```

对应 service 会每 15 分钟轮询一次 due jobs，并：

- 进入 `/home/ubuntu/极简 crm`
- source `/home/ubuntu/.openclaw-wecom-pg.env`
- 执行 `python scripts/run_automation_conversion_due_jobs.py`

如果暂时仍使用 cron，至少统一改成调用仓库脚本，而不是继续把 curl 命令散落在 crontab 里：

```cron
 */15 * * * * cd /home/ubuntu/极简\ crm && \
  source /home/ubuntu/.openclaw-wecom-pg.env && \
  source /home/ubuntu/venvs/openclaw/bin/activate && \
  python scripts/run_automation_conversion_due_jobs.py >> /var/log/aicrm/automation_conversion_due_runner.log 2>&1
```

如果 runner 没挂上，会出现：

- `/admin/automation-conversion/programs/<program_id>/flow-design?section=sop` 能正常配置
- 但 `recent_batches` 长时间无新记录
- 成员不会按 day 推进发送

## 7. 线上只读 smoke 顺序

先做只读检查，再做写操作：

```bash
curl -sS http://127.0.0.1:5001/health
sudo systemctl status openclaw-wecom-postgres.service --no-pager
sudo journalctl -u openclaw-wecom-postgres.service -n 100 --no-pager
```

后台只读确认：

- `/admin/automation-conversion`
- `/admin/questionnaires`
- `/admin/customers`

## 8. 如果发现问题，怎么快速回退到“只读/停用”状态

### 8.1 OpenClaw webhook 异常

止损动作：

- 把 `OPENCLAW_WEBHOOK_URL` 清空

影响：

- 重点跟进池来消息不再推送 OpenClaw
- CRM 主链路、问卷、切池、侧边栏、激活回写不受影响

### 8.2 问卷提交外发 webhook 异常

止损动作：

- 把 `QUESTIONNAIRE_SUBMIT_WEBHOOK_URL` 清空

影响：

- 问卷仍可正常提交
- 只是不再外发 mobile / userid / unionid webhook

### 8.3 激活回写 webhook 异常

止损动作：

- 临时下掉外部调用方
- 或把 `AUTOMATION_INTERNAL_API_TOKEN` 换成新值，拒绝旧流量
- 如果仍保留 legacy 兼容，再同步轮换 `AUTOMATION_ACTIVATION_WEBHOOK_TOKEN`

影响：

- 激活回写入口暂停
- 其它主链路不受影响

### 8.4 池子群发异常

止损动作：

- 暂停使用 MCP 工具 `send_pool_private_message`
- 或临时替换 `AUTOMATION_INTERNAL_API_TOKEN`
- 如果仍保留 legacy 兼容，再同步替换 `MCP_BEARER_TOKEN`

影响：

- OpenClaw 无法再直接发起池子群发
- CRM 其它链路不受影响

### 8.5 自动 SOP runner 异常

止损动作：

- 先停掉 cron / timer，不再触发 `/api/admin/automation-conversion/sop/run-due`
- 保留原有 `manual-send` 和 `focus batch`
- 后台页面 no-JS 表单兜底入口使用 `POST /admin/automation-conversion/programs/<program_id>/member-ops/stage/<stage_key>/send`；旧 `/admin/automation-conversion/stage/<stage_key>/send` 已下线

影响：

- 自动 SOP 停止继续发送
- 手工群发和 focus AI 批任务继续可用

### 8.6 需要临时停自动化转化

止损动作：

- 进入 `/admin/automation-conversion`
- 关闭“开启自动化转化问卷初判”

影响：

- 自动化转化问卷初判和后续路由停止继续推进
- 已有历史记录仍保留
- 手工侧边栏查看和人工动作仍可继续

## 9. 如果发现 webhook 异常怎么降级

推荐降级顺序：

1. 先只停出问题的 webhook
2. 保留 CRM 主流程
3. 继续做只读验收和人工验收
4. 如果问题扩散到核心切池或提交链路，再考虑关闭自动化转化开关

## 10. 线上日志检查建议

优先查：

```bash
sudo journalctl -u openclaw-wecom-postgres.service -f
```

关注关键词：

- `questionnaire submit webhook`
- `openclaw focus message webhook`
- `activation_webhook`
- `send_pool_private_message`
- `invalid internal token`
- `missing internal token`

## 11. 统一鉴权核对建议

线上至少验证以下动作型接口都被统一 Bearer Token 保护：

1. `/mcp`
2. `/api/customers/automation/activation-webhook`
3. `/api/customers/automation/webhook-deliveries/retry-due`
4. `/api/admin/jobs/webhook-deliveries/run`

最小核对方法：

- 正确 token 调用返回成功
- 错 token 调用统一返回 `401`
- 公开问卷提交接口 `/api/h5/questionnaires/<slug>/submit` 仍保持可用

同时检查：

- 后台发送记录
- 客户当前池子
- 侧边栏状态
