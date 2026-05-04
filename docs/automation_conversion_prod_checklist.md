# 自动化转化线上总验收 Checklist

## 配置检查

- [ ] `AUTOMATION_INTERNAL_API_TOKEN` 已配置
- [ ] `MCP_BEARER_TOKEN` 如仍保留 legacy 兼容，已确认与统一 token 不冲突
- [ ] `OPENCLAW_WEBHOOK_URL` 已配置
- [ ] `AUTOMATION_ACTIVATION_WEBHOOK_TOKEN` 如仍保留 legacy 兼容，已确认与统一 token 不冲突
- [ ] `QUESTIONNAIRE_SUBMIT_WEBHOOK_URL` 已配置
- [ ] `QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN` 已配置
- [ ] `MESSAGE_ACTIVITY_DB_HOST/PORT/NAME/USER/PASS` 已配置
- [ ] 企微相关配置已配置
- [ ] 错误内部 token 调动作型接口会返回 401
- [ ] `openclaw-automation-conversion-due-runner.timer` 已安装并处于 active，15 分钟轮询执行自动化运营 due jobs

## 问卷检查

- [ ] 自动化转化问卷已配置
- [ ] 问卷包含必填手机号题
- [ ] 关键题配置正常
- [ ] 提交成功后手机号正常保存

## 池子检查

- [ ] 新用户池可进入
- [ ] 未激活普通池可进入
- [ ] 未激活重点跟进池可进入
- [ ] 激活普通池可进入
- [ ] 激活重点跟进池可进入
- [ ] 沉默池可进入

## 侧边栏检查

- [ ] 当前池子展示正确
- [ ] 当前是否激活展示正确
- [ ] 当前跟进类型展示正确
- [ ] 普通/重点人工改判可用
- [ ] 人工确认成交可用

## 自动化转化群发检查

- [ ] 首页每个阶段都能点击 `创建群发`
- [ ] `new-user / inactive-normal / active-normal / silent / won` 可走官方群发
- [ ] 官方群发当前支持 `文本 + 图片`
- [ ] 当前按单发送人模型执行，不做 owner filter / owner 分桶
- [ ] `inactive-focus / active-focus` 可创建 OpenClaw AI 批任务
- [ ] AI 批任务通过后台 runner 推进，不在请求里 sleep
- [ ] 发送记录可查

## 自动 SOP 检查

- [ ] `/admin/automation-conversion/programs/<program_id>/flow-design?section=sop` 可打开
- [ ] 只出现 `new_user / inactive_normal / active_normal` 三个 SOP 池
- [ ] 三个 pool config 可保存
- [ ] `max_day_count` 扩容会自动补空模板
- [ ] `max_day_count` 缩容不会删除高 day 模板
- [ ] 模板支持保存文本和图片 `image media_id`
- [ ] 文案明确说明“重复进同池不重来、离池期间错过不补发、名单执行时现算、与手工群发不去重”
- [ ] `POST /api/admin/automation-conversion/sop/run-due` 可正常执行
- [ ] run-due 同一天重跑幂等，不会重复给同一 member + pool + day 发送
- [ ] `recent batch` 列表可看到 `pool / day / scheduled_for / status / total / success / skipped / failed`

## 焦点消息 webhook 检查

- [ ] 重点跟进池客户来消息会推送 webhook
- [ ] 普通池客户来消息不会推送
- [ ] payload 关键字段完整
- [ ] 失败日志可查

## 激活回写检查

- [ ] 按手机号回写成功
- [ ] 未激活普通 -> 激活普通
- [ ] 未激活重点 -> 激活重点
- [ ] 已激活重复回写只刷新时间

## 问卷提交 webhook 检查

- [ ] 提交成功后会外发 webhook
- [ ] 字段为 mobile / userid / unionid
- [ ] webhook 异常不影响问卷主提交流程

## 成交退出营销检查

- [ ] 人工确认成交后状态变成 `converted/enrolled`
- [ ] 成交后不再 eligible for conversion

## 日志 / 发送记录检查

- [ ] service 日志能看到关键动作
- [ ] 发送记录能查到官方群发记录
- [ ] focus batch 和 item 状态可查
- [ ] webhook 失败有日志痕迹

## 异常处理与回退检查

- [ ] OpenClaw webhook 可单独停用
- [ ] 问卷 webhook 可单独停用
- [ ] 激活回写入口可单独停用
- [ ] 池子群发可单独停用
- [ ] 自动化转化问卷初判可整体停用
