# Deploy Runbook

这份文档描述当前最常用的本地开发和生产发布口径。

当前代码默认运行入口已经切到 AI-CRM Next：

```bash
python3 app.py run
```

旧 Flask 只作为 legacy fallback：

```bash
python3 app.py run-legacy
python3 legacy_flask_app.py run
```

这次入口变更本身不修改生产 Nginx/systemd，不代表生产流量已经切换。

## 本地仓库约定

- 当前 Git clone 就是本地唯一正式工作目录
- 新任务统一从最新 `main` 开分支
- 不再通过复制多个项目目录来并行开发

建议开始开发前先做：

```bash
git switch main
git pull --ff-only origin main
git switch -c <feature-branch>
```

## 生产环境

- 外网入口：`https://www.youcangogogo.com`
- systemd 服务：`openclaw-wecom-postgres.service`
- 商品支付外部推送 worker：`openclaw-external-push-worker.timer` / `openclaw-external-push-worker.service`
- Nginx 上游：`http://127.0.0.1:5001`
- 生产代码目录：`/home/ubuntu/极简 crm`
- 环境变量文件：`/home/ubuntu/.openclaw-wecom-pg.env`
- 生产虚拟环境：`/home/ubuntu/venvs/openclaw/bin/activate`

当前线上正式流量只走 `5001`。生产服务命令是否改为 Next 仍需单独人工审批。

不要再默认假设：

- 存在长期运行的 `5000` 冷备实例
- 服务器上存在多份并行有效的发布目录

## 常用只读检查

```bash
curl -sS http://127.0.0.1:5001/health
sudo systemctl status openclaw-wecom-postgres.service --no-pager
sudo journalctl -u openclaw-wecom-postgres.service -n 100 --no-pager
```

常用页面：

- `/admin`
- `/admin/customers`
- `/admin/questionnaires`
- `/admin/automation-conversion`
- `/admin/jobs`

## 发布口径

当前生产发布仍是手工同步，但源码基线统一来自 GitHub `main`。
GitHub Actions 里 `main` push 只跑关键路径 smoke，避免每个小 PR 合并后
都等待全量 PG 回归；完整 `full-test` 保留在 nightly 和手动触发。

AI-CRM Next 已经成为默认代码入口，但生产 route/systemd/Nginx 切换仍必须走人工签核。

推荐顺序：

1. 在本地最新 `main` 上开发和测试
2. 提交分支并合并到 GitHub `main`
3. 服务器部署时只同步已经合入 `main` 的代码
4. 同步到 `/home/ubuntu/极简 crm`
5. 必要时安装依赖并执行数据库初始化
6. 确认本次是否已获批切换 systemd 命令；未获批时保持 legacy fallback 命令
7. 重启 `openclaw-wecom-postgres.service`
8. 做只读验收

## 典型发布步骤

```bash
cd /home/ubuntu/极简\ crm
set -a
source /home/ubuntu/.openclaw-wecom-pg.env
set +a
test -n "${DATABASE_URL:-}"
source /home/ubuntu/venvs/openclaw/bin/activate
python3 -m pip install -r requirements.txt
# AI-CRM Next default runtime:
python3 app.py health

# Legacy database initialization remains explicit:
python3 app.py init-db-legacy
sudo systemctl restart openclaw-wecom-postgres.service
curl -sS http://127.0.0.1:5001/health
sudo cp deploy/openclaw-external-push-worker.service /etc/systemd/system/
sudo cp deploy/openclaw-external-push-worker.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable openclaw-external-push-worker.timer
sudo systemctl restart openclaw-external-push-worker.timer
sudo systemctl start openclaw-external-push-worker.service
sudo systemctl status openclaw-external-push-worker.timer --no-pager
```

不要在未经审批时修改生产 Nginx、systemd 或 route flag。不要把本地/staging evidence 写成 production canary 已执行。

## 日志与备份

- service 日志：
  - `sudo journalctl -u openclaw-wecom-postgres.service -f`
- 自动化 due runner 日志：
  - `sudo journalctl -u openclaw-automation-conversion-due-runner.service -f`
  - `sudo systemctl status openclaw-automation-conversion-due-runner.timer --no-pager`
- 商品支付外部推送日志：
  - `sudo journalctl -u openclaw-external-push-worker.service -f`
  - `sudo systemctl status openclaw-external-push-worker.timer --no-pager`
- Nginx 日志：
  - `/var/log/nginx/access.log`
  - `/var/log/nginx/error.log`
- archive sync / backup 日志：
  - `/home/ubuntu/openclaw-cron.log`
  - `/home/ubuntu/openclaw-pg-backup.log`
- PostgreSQL 备份目录：
  - `/home/ubuntu/backups/openclaw-postgres/`

## 仓库与服务器清洁约定

- 服务器生产目录只保留一份正式代码
- smoke 目录、手工同步副本、历史发布包和 macOS 元数据不要长期堆在服务器
- 本地主仓不提交 `dist/`、`exports/`、顶层归档包、旧静态草稿页面

## 真实环境验收顺序

1. 先看服务和日志
2. 再看 `/health`
3. 再看关键页面和接口是否在线
4. 最后才做业务验收或写操作
