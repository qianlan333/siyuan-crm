# 自动化转化验收 Checklist

## 主链路入口

- [ ] `/admin/automation-conversion` 可正常打开
- [ ] 首页每个阶段卡都同时提供 `查看名单` 和 `创建群发`
- [ ] `/admin/automation-conversion/programs/<program_id>/member-ops?stage=<stage_key>&panel=members` 可正常打开
- [ ] `/admin/automation-conversion/programs/<program_id>/member-ops?stage=<stage_key>&panel=send` 可正常打开
- [ ] 当前只保留自动化转化主链路，不依赖旧兼容页或 `user_ops` 页面

## 自动启动时间窗

- [ ] 设置页可编辑 `day_start_hour`
- [ ] 设置页可编辑 `quiet_hour_start`
- [ ] 首页和设置页都能看到“自动启动时间窗”说明
- [ ] `08:59` 不允许新启动
- [ ] `09:00` 允许新启动
- [ ] `22:59` 允许新启动
- [ ] `23:00` 不允许新启动
- [ ] `day_start_hour >= quiet_hour_start` 时保存直接报错

## 默认渠道二维码

- [ ] 设置页可编辑默认渠道欢迎语
- [ ] 设置页可编辑“免验证直接添加好友”开关
- [ ] 保存后再次进入设置页能正确读回
- [ ] 生成默认二维码时会把 `welcome_message / auto_accept_friend` 一起带入 provider
- [ ] provider 不支持欢迎语时，会明确显示 `unsupported`
- [ ] provider 支持免验证时，会明确显示 `pending / applied`

## 首页消息活跃同步

- [ ] 首页可直接点击“立即刷新一次”
- [ ] 点击后有 loading 和防重复点击
- [ ] 首页可看到最近一次同步摘要
- [ ] 设置页同步入口继续可用
- [ ] 未配置消息库时，首页和设置页都显示 `not_configured`，不伪造 failed 记录

## 阶段页与发送页

- [ ] 首页阶段卡不再展示“重点跟进 / 普通跟进”指标
- [ ] 阶段详情页顶部不再展示“重点跟进 / 普通跟进”指标
- [ ] 阶段详情页顶部保留 `总人数 / 今日新增`
- [ ] 所有阶段都能进入 send 页面，包括 `silent / won`
- [ ] focus 阶段进入 `AI 批量处理` 壳子
- [ ] 非 focus 阶段进入 `官方群发` 壳子

## 非重点阶段官方群发

- [ ] `new-user` 可发
- [ ] `inactive-normal` 可发
- [ ] `active-normal` 可发
- [ ] `silent` 可发
- [ ] `won` 可发
- [ ] 发送名单来自当前自动化阶段成员，不走主表手工筛选
- [ ] 当前按单发送人模型执行，不做 owner filter / owner 分桶
- [ ] 缺失 `external_userid` 的成员会跳过，并返回 `skipped_count / skipped_reasons`
- [ ] 发送结果会返回 `ok / stage_key / total_target_count / sent_count / skipped_count / skipped_reasons / record_id / task_ids`

## 重点阶段 OpenClaw 批任务

- [ ] `inactive-focus` 可创建批任务
- [ ] `active-focus` 可创建批任务
- [ ] 批任务按创建时的阶段名单快照入库
- [ ] runner 每次只推进到期 item
- [ ] 节奏固定为每 `20` 秒推进 `1` 个
- [ ] 批任务不是在 HTTP 请求里 `sleep` 串行执行
- [ ] 同一阶段已有进行中批任务时，会拦截并发创建
- [ ] 单 item 失败不会拖死整批
- [ ] 单 item 命中 cooldown 时记为 `skipped`

## OpenClaw 单客推送

- [ ] 侧边栏/单客“一键自动化写话术”继续返回 `accepted`
- [ ] 30 秒 cooldown 继续生效
- [ ] 顶层 payload 只包含：
  - `externalContactId`
  - `currentPool`
  - `currentStage`
  - `currentTarget`
  - `tags`
  - `questionnaire`
  - `recentChats`

## 明确不做的范围

- [ ] 不新增 owner filter
- [ ] 不新增“可群发人数”卡片
- [ ] 不恢复素材库
- [ ] 不恢复富文本编辑
- [ ] 不做多负责人二维码管理
