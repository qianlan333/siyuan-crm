# siyuan AI-CRM Next 生产切换报告模板

> 本模板只记录脱敏结果。不要写入完整 `DATABASE_URL`、密码、token、secret、AESKey、私钥、raw `external_userid`、raw `scene_value`、手机号、unionid、openid。

## 1. 基本信息

- 执行时间：
- 执行人：
- 代码 commit：
- 旧 release 路径：
- 新 release 路径：
- 旧 DB 标识（库名/环境名，不写完整 URL）：
- 新 DB 标识（库名/环境名，不写完整 URL）：
- 是否采用新生产库切换：
- 是否修改 systemd/nginx：

## 2. 最终备份

| 项目 | 路径 | 大小 | 结果 |
| --- | --- | --- | --- |
| dump |  |  |  |
| env backup |  |  |  |
| assets archive |  |  |  |

备注：

## 3. 初始化命令结果

| 命令 | 结果 | 备注 |
| --- | --- | --- |
| `python3 app.py health` |  |  |
| `python3 app.py init-db` |  |  |
| `python3 app.py init-next-schema-safe` |  |  |
| `python3 app.py sync-customer-read-model --dry-run` |  |  |
| `python3 app.py sync-customer-read-model` |  |  |

## 4. Projection Sync 结果

- source_customer_count：
- projected_customer_count：
- customer_detail_snapshot_next count：
- customer_list_index_next count：
- customer_timeline_event_next count：
- customer_recent_message_next count：
- projection coverage against contacts：
- projection coverage against external_contact_bindings：
- skipped_count：
- skipped_reasons：

## 5. Channel Backfill 结果

- automation_channel count：
- scene_value_non_empty：
- scene_alias_coverage：
- qrcode_asset_coverage：
- runtime diagnosis 抽样数量：
- runtime diagnosis 结果（scene 必须脱敏）：

## 6. Smoke Test 结果

| Endpoint / 动作 | 状态 | 备注 |
| --- | --- | --- |
| `/health` |  |  |
| `/admin` |  |  |
| `/admin/channels` |  |  |
| `/admin/customers` |  |  |
| `/admin/config` |  |  |
| `/admin/api-docs` |  |  |
| `/api/admin/user-ops/overview` |  |  |
| `/api/customers/{external_userid}` |  | external_userid 必须脱敏 |
| `/api/customers/{external_userid}/timeline` |  | external_userid 必须脱敏 |
| `/api/sidebar/customer-context` |  | external_userid 必须脱敏 |
| `/api/sidebar/profile` |  | external_userid 必须脱敏 |
| 旧渠道码扫码路径 |  | scene 必须脱敏 |
| 订单/问卷/侧边栏基础链路 |  | 如启用 |

## 7. Callback 验证结果

- 企业微信 callback GET 校验：
- 企业微信 callback POST 日志：
- 公众号 OAuth redirect：
- 微信/企微验证文件访问：

## 8. 观察窗口结果

- 观察开始时间：
- 观察结束时间：
- 5xx 日志：
- 企业微信 callback 日志：
- DB connection count：
- user-ops overview：
- customer/sidebar API：
- channel runtime diagnosis：
- 最近新增客户归因：
- 自动化任务：
- 队列/worker：
- 未覆盖项：

## 9. Go / Rollback

- 是否 Go：
- 是否执行回滚：
- 回滚类型：
- 回滚时间：
- 回滚验证结果：

## 10. 遗留问题

- 问题：
- 影响范围：
- 负责人：
- 下一步：

## 11. 安全声明

- 未提交 `.env`、dump、uploads、instance、pem/key：
- 未在报告中记录完整 `DATABASE_URL`：
- 未在报告中记录密码、token、secret、AESKey、私钥：
- 未在报告中记录 raw `external_userid`、raw `scene_value`、手机号、unionid、openid：
- 未对生产库执行未授权的 `DROP` / `CLEAN` / `pg_restore`：
