# 黄小璨使用数据同步运行手册

## 边界

- 黄小璨 MySQL 连接仅由 `scripts.run_huangyoucan_usage_sync` 使用，管理页和侧边栏请求不访问外库。
- 外库账号必须是独立只读账号，并完成 AI-CRM 生产出口 IP 白名单配置。
- 本地投影不保存明文手机号或消息内容，只保存黄小璨用户 ID、unionid、手机号 MD5、聚合指标和刷新时间。
- 同步采用单事务整批替换；失败会回滚并保留上次成功快照，同时写入失败运行记录。

## 配置

在生产主机创建仅 `ubuntu` 可读的 `/home/ubuntu/.aicrm-huangyoucan-readonly.env`：

```dotenv
AICRM_HUANGYOUCAN_DB_HOST=
AICRM_HUANGYOUCAN_DB_PORT=3306
AICRM_HUANGYOUCAN_DB_NAME=
AICRM_HUANGYOUCAN_DB_USER=
AICRM_HUANGYOUCAN_DB_PASSWORD=
AICRM_HUANGYOUCAN_DB_CONNECT_TIMEOUT_SECONDS=10
AICRM_HUANGYOUCAN_DB_READ_TIMEOUT_SECONDS=60
```

不要把真实值、数据库访问文档或连接命令提交到仓库。

## 首次启用

1. 执行迁移：`python -m alembic upgrade head`。
2. 配置独立只读账号、出口 IP 白名单和环境文件权限。
3. 只读预检：`python -m scripts.run_huangyoucan_usage_sync --dry-run --operator production_dry_run`。
4. 首次同步：`python -m scripts.run_huangyoucan_usage_sync --operator production_initial_sync`。
5. 验证两张投影表的刷新时间、行数和最近运行状态，再验收成员 API、周期数据页和侧边栏周期订单。
6. 将 `aicrm-huangyoucan-usage-sync.timer` 从 runtime manifest 的批准态按生产变更流程启用，确认 `systemctl list-timers` 中下一次北京时间 09:00 或 21:00 触发。

## 回滚

先停用 `aicrm-huangyoucan-usage-sync.timer`，再回滚应用到上一精确 release SHA。`0107` 新增表可以保留，旧版本不会读取；不要为了应用回滚删除最后成功快照或同步审计记录。
