# siyuan-crm

## siyuan-crm upgraded by AI-CRM Next

当前 `siyuan-crm` 已升级为 AI-CRM Next 产品基线：`python3 app.py run` 默认启动 `aicrm_next.main:app`，旧 Flask 仅作为 `python3 app.py run-legacy` / `python3 legacy_flask_app.py run` 的 legacy fallback。

迁移文档见 [docs/siyuan_aicrm_next_migration.md](docs/siyuan_aicrm_next_migration.md)。生产数据、授权配置、验证文件和上传资产不在仓库中，需要按迁移文档备份、恢复到预发库并完成校验后再切换生产。

不要提交 `.env`、数据库 dump、`uploads/`、`static/uploads/`、`instance/`、`*.pem` 或 `*.key` 文件。

## 快速启动

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 app.py run
```

默认监听 `http://127.0.0.1:5001`，可通过 `APP_HOST` / `APP_PORT` 覆盖。

## 迁移与验收

仓库级迁移脚本位于 `scripts/siyuan_migration/`：

- `00_preflight.sh`
- `01_backup_current_assets.sh`
- `02_restore_to_staging_db.sh`
- `03_channel_backfill.sql`
- `04_validate_migration.sql`
- `05_smoke_test.sh`

生产切换前必须先在 `siyuancrm_next` 预发库完成备份恢复、schema 初始化、渠道码 backfill、数据校验和 smoke test。
