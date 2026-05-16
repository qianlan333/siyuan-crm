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

`tests/integration/conftest.py` 的 `app` fixture 复用顶层 `tests.conftest.build_pg_test_app`；没配 `DATABASE_URL` 时整组 integration test 会 skip。每个 test 跑前由共享 fixture `TRUNCATE` 关键表，保证隔离。

CI 上 GitHub Actions 用 service container 起 postgres:16，自动设 `DATABASE_URL`，每个 PR 必跑。

## 现在覆盖了什么

| 测试 | 关联 PR | 验证 |
|---|---|---|
| `test_pg_bug_184_185_187_approval_token_issue_consume` | #184 / #185 / #187 | token 全流程 issue → consume → race / mismatch |
| `test_pg_bug_184_185_token_timezone_aware_storage` | #185 | `expires_at` 真按 UTC 存（不被 server tz 倒推） |
| `test_pg_bug_202_frequency_budget_select_with_bool` | #202 | `WHERE enabled` 不抛 `boolean = integer` |
| `test_pg_bug_192_200_206_scheduler_full_cycle_batch` | #192 / #200 / #206 | 启动 + 调度 + batch dispatch（N 人 1 个 task） |
| `test_pg_bug_200_register_member_reply_clears_next_due` | #200 | `register_member_reply` 把 next_due_at 清空（PG NULL） |
| `test_pg_image_library_crud_smoke` | image_library | CRUD |

## 怎么加新的 smoke

发现 / 怀疑某个新代码路径有 PG 兼容风险时，在 `tests/integration/test_pg_compat_smoke.py` 加 test 函数。

最小模板：

```python
def test_pg_my_new_path(app):
    """覆盖 ... 路径，关联 PR #XXX。"""
    from wecom_ability_service.domains.foo import bar
    
    # 调你想验证的函数（直接走真 SQL）
    result = bar.do_something()
    assert result["ok"]
```

`app` fixture 已经把 Flask app context 启好 + DB schema 建好，直接调业务函数就行。如果需要造数据，参考 `_insert_segment_with_known_member`。

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
