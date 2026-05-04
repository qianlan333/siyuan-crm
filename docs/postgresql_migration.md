# PostgreSQL Migration

## 1. 初始化 PostgreSQL

创建数据库后执行：

```bash
psql "$DATABASE_URL" -f wecom_ability_service/schema_postgres.sql
```

示例：

```bash
export DATABASE_URL='postgresql://openclaw:OpenclawPg2026@127.0.0.1:5432/openclaw_wecom'
psql "$DATABASE_URL" -f wecom_ability_service/schema_postgres.sql
```

## 2. SQLite -> PostgreSQL 一次性迁移

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-path "/home/ubuntu/极简 crm/data.sqlite3" \
  --database-url "$DATABASE_URL" \
  --schema-path wecom_ability_service/schema_postgres.sql
```

如需覆盖已有测试数据：

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-path "/home/ubuntu/极简 crm/data.sqlite3" \
  --database-url "$DATABASE_URL" \
  --schema-path wecom_ability_service/schema_postgres.sql \
  --truncate-target
```

## 3. PostgreSQL 备份

```bash
export DATABASE_URL='postgresql://openclaw:OpenclawPg2026@127.0.0.1:5432/openclaw_wecom'
bash scripts/backup_postgres.sh
```

## 4. PostgreSQL 恢复

```bash
export DATABASE_URL='postgresql://openclaw:OpenclawPg2026@127.0.0.1:5432/openclaw_wecom'
bash scripts/restore_postgres.sh /home/ubuntu/backups/openclaw-postgres/openclaw-YYYYMMDD-HHMMSS.dump
```

## 5. 回滚

如果 PostgreSQL 版服务验证失败：

1. 保持 SQLite 数据文件不动：
   - `/home/ubuntu/极简 crm/data.sqlite3`
2. 将 `systemd` 或启动脚本中的 `DATABASE_URL` 移除
3. 恢复原 SQLite 启动命令并重启服务
