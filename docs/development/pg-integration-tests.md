# PG 兼容性回归测试

为什么有这套测试：2026-05 一周内连续踩了 **6 个 PG 兼容 bug**（PR #184 / #185 / #187 / #192 / #200 / #202），每一个都因为 SQLite 上跑得过、PG 上炸。修复链路是「报错 → SSH 抓 traceback → 改代码 → 部署 → 还有下一个」。CI 上跑 PG 集成测试是终结这种循环的唯一办法。

任何引入 SQLite-only 写法（`= 1` 比 BOOLEAN、`substr(TIMESTAMPTZ)`、`WHERE ts <> ''`、`SET ts = ''` 等）的 PR 会让 GitHub Actions 的 `pg-smoke` job 挂掉，**部署前**就被拦下来。

## 跑

### PG 模式

需要本地有 PG 16+：

```bash
# 起 PG（docker 一行）
docker run -d --rm --name pg-test \
  -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test \
  -p 5432:5432 postgres:16

# 跑测试
DATABASE_URL=postgresql://test:test@localhost:5432/test pytest tests/integration/

# 跑完清理
docker stop pg-test
```

旧的 `historical removed reference (test_pg_compat_smoke.py)` 已随 legacy package/domain executable tests 归档。新的 PG smoke 应放到对应 Next-native owner 测试文件中，并通过 `DATABASE_URL` 在真实 PG 上运行。

CI 上 GitHub Actions 用 service container 起 postgres:16，自动设 `DATABASE_URL`，每个 PR 必跑。

## 现在覆盖了什么

| 测试 | 验证 |
|---|---|
| `tests/test_marketing_schema_init.py` | Next-owned marketing/user-ops fixture repo smoke |
| `tests/test_campaigns_due_calc.py` | campaign due calculation on current data shape |
| `tests/test_broadcast_jobs_service.py` / `tests/test_run_broadcast_queue_worker.py` | broadcast queue lifecycle and worker contracts |
| `historical removed reference (test_post_closeout_production_contract.py)` | post-closeout production runtime contract |

## 怎么加新的 smoke

发现 / 怀疑某个新代码路径有 PG 兼容风险时，在对应的 Next-native test file 中加覆盖。例如 campaign 放在 `tests/test_campaign*.py`，broadcast 放在 `tests/test_broadcast*.py`，schema bootstrap 放在 `tests/test_marketing_schema_init.py` 或对应 domain 的 schema/contract test。

最小模板：

```python
def test_pg_my_new_path():
    """覆盖 ... 路径，关联 PR #XXX。"""
    from aicrm_next.some_domain import service
    
    # 调你想验证的函数（直接走真 SQL）
    result = service.do_something()
    assert result["ok"]
```

不要新增 legacy Flask app context 或 `wecom_ability_service` import；需要造数据时使用对应 Next repo/service/fake fixture。

## 如果 CI 挂了

`pg-smoke` job 失败时第一时间看 traceback：

- `psycopg.errors.UndefinedFunction: function substr(timestamp ...)` → 又一处 `substr(TIMESTAMPTZ)` 漏改
- `psycopg.errors.InvalidDatetimeFormat: ...""` → 又一处 `SET ts = ''` 或 `WHERE ts <> ''`
- `psycopg.errors.UndefinedFunction: operator does not exist: boolean = integer` → 又一处 `WHERE bool_col = 1`
- `psycopg.errors.DatatypeMismatch: column "x" is of type boolean but expression is of type smallint` → 又一处 INSERT `1 if x else 0` 给 BOOLEAN 字段

修法跟前 6 个 PR 同款：grep 全文找同类写法，统一改用 `_empty_ts() / WHERE col / bool(x)` 这些 PG-safe helper / 写法。

## 路线（后续可做）

- [ ] 把更多关键路径加进来：reply_monitor 异步 → register_member_reply、CSV 导出、observability 报表 SQL 等
- [ ] 加性能 budget 类断言（process_due_campaign_members 100 人不超过 1s 之类）
- [ ] 继续把更多普通单测迁到共享 PG fixture，减少旧 SQLite 形状的测试脚手架
