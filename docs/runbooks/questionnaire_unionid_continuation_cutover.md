# 问卷 UnionID 续接生产切换

## 发布顺序

1. 先发布数据库与代码，保持 `AICRM_QUESTIONNAIRE_UNIONID_REQUIRED=0`、`AICRM_QUESTIONNAIRE_CONTINUATION_ENABLED=0`。
2. 确认 Web、回调收件箱、内部事件 worker、External Effect worker、AI Audience scheduler 和问卷续接 timer 都运行在同一 release SHA。
3. 在真实微信内打开任一已发布问卷的 OAuth 地址，完成一次受控测试账号授权。
4. 在生产主机执行只读门禁检查：

   ```bash
   python scripts/ops/check_questionnaire_unionid_cutover.py --require-real-proof
   ```

   只有 `ready_to_enable_unionid_gate=true` 才能继续。检查结果只输出 UnionID/OpenID 哈希，不输出原值。
5. 在生产环境文件中同时开启：

   ```text
   AICRM_QUESTIONNAIRE_UNIONID_REQUIRED=1
   AICRM_QUESTIONNAIRE_CONTINUATION_ENABLED=1
   AICRM_INTERNAL_EVENTS_ENABLED=1
   ```

   如果 `AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES` 非空，必须在原值中追加
   `customer.wecom_identity_ready`；不得覆盖或移除原有事件类型。

   通过仓库的生产 runtime unit 管理脚本重启 Web、回调 worker、内部事件 worker 与问卷续接 timer；禁止手工另建旁路进程。
6. 先预览近 7 天回补：

   ```bash
   python scripts/backfill_questionnaire_continuations.py
   ```

   确认候选仅含 `wechat_oauth_signed_session` 验证记录后，再执行：

   ```bash
   python scripts/backfill_questionnaire_continuations.py --apply
   ```

## 真实验收

使用受控账号完成：OAuth 获取 UnionID → 提交问卷并展示既有企微二维码 → 从任意入口添加企微 → 回调客户详情同步 → `customer.wecom_identity_ready` → 标签 External Effect 获得企微成功回执 → 对应 Agent 批次和内容产生。

`questionnaire_continuation_job.status=dispatched` 只表示已移交下游，不能作为企微成功或消息发送成功证据。运营页需同时检查 External Effect、Agent 批次及发送记录。

## 回滚

1. 将两个门禁开关同时设为 `0`，停止新续接唤醒。
2. 使用生产 runtime unit 管理脚本重启相关服务。
3. 不删除 `questionnaire_submissions`、`questionnaire_continuation_job` 或内部事件数据。
4. 不撤销已派发的 External Effect、Agent 批次或已发送消息；如需处理，按对应下游的独立运营流程执行。

## 禁止项

- 不使用手机号或普通 OpenID 回补、匹配或选择客户身份。
- 不在企微回调请求内同步打标签、调用模型或发送消息。
- 身份冲突或负责人不明确时不任选一个身份继续。
- 不以 HTTP 200、内部事件成功或 `dispatched` 代替真实提供商回执。
