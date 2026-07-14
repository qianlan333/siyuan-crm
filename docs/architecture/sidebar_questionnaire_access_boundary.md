# Sidebar、Customer Detail 与 Questionnaire Result 访问边界

状态：R04 强制封口。适用于测试环境先行发布；生产提升必须复用同一精确 release SHA。

## 入口清单

| Surface | 入口数 | 认证与授权 | PII 风险 | R04 决策 |
| --- | ---: | --- | --- | --- |
| Sidebar bootstrap（JSSDK、OAuth start/callback） | 3 | 企微 OAuth；callback 再查当前 owner/follow | 员工、客户标识 | 只允许 OAuth viewer session 签发 v2 context |
| Sidebar read | 16 | v2 signed context + OAuth session + customer + corp + 当前 owner/follow | 手机号、标签、问卷摘要、订单 | 无可信 viewer 或关系即 401/403；不返回 PII |
| Sidebar write | 9 | 与 read 相同，并在 CommandBus 前再次查询当前关系 | 客户资料和状态修改 | actor/owner 固定来自可信 context；body/query 只能一致，不能覆盖 |
| Customer read/detail（external、unionid、mobile） | 13 | 后台入口走 admin session capability；sidebar 入口走 staff owner scope | 手机号、unionid、标签、答案与消息 | identity resolve 仅定位，不代表授权；读数据前仍校验 capability/scope |
| Public questionnaire result | 1 | 随机 result token + 短期 HttpOnly grant cookie | 答案、身份与评分 | URL 单独不再是 bearer；跨浏览器、过期、tamper、顺序 ID 均为 403 |
| Admin questionnaire result/submission | 2 | admin session + `admin_read` capability | 问卷答案与身份 | 保留后台合法读取，不复用公共 grant |

Sidebar 页面 `/sidebar/bind-mobile` 保持原 URL。前端继续从 JSSDK bootstrap 获取 header token；缺 session 时沿现有 OAuth 自动跳转，不新增人工步骤。

## 唯一可信链

1. OAuth callback 取得企微员工 userid。
2. 服务端查询目标 external contact 当前有效 follow、identity map 或 canonical owner 关系；历史 first/last owner 不参与授权。
3. 服务端写入 HttpOnly viewer session，包含 corp、customer、随机 session id。
4. JSSDK bootstrap 签发 15 分钟 v2 context，绑定 viewer、customer、corp 与 session-id 指纹。
5. 中间件和 endpoint 都只从 header + cookie 读取可信 context；query token、query/header viewer、admin session 代替 sidebar OAuth 均被拒绝。
6. read model 在 identity resolve 后再次核对当前 owner/follow；write model 在命令执行前再次查询关系，因此已撤权关系不能靠旧 token 重放。

## 已删除路径

- `allow_readonly_fallback`、owner-pending sentinel、无 owner 的只读 shell。
- production `skip-owner`。
- request-declared actor、header actor、query/header viewer。
- 单 owner identity fallback 自动签发 token。
- query-string sidebar owner token。
- 仅凭 questionnaire result URL 读取结果。
- `external_contact_bindings.first_owner_userid/last_owner_userid` 作为授权来源。

静态门禁：

```bash
python scripts/ci/check_sidebar_questionnaire_access_contract.py
```

目标输出：`unsafe_fallback_count=0`、`actor_override_count=0`、`tokenless_result_count=0`。

## Count-only 数据预检

2026-07-11 的 R04 前只读生产形态抽查（不输出身份原值）：

- 任一当前 owner source 覆盖 external contact：23,847。
- active follow：23,844。
- identity map：23,844。
- canonical owner（当时为非 `deleted` 统计口径）：23,783。R04 运行时与 checker
  已收紧为仅 `active`，该旧数不作为授权放行依据。
- 旧口径下仅历史 binding、无 owner source：3。R04 的 `active` 口径可能阻断更多
  `pending_merge/conflict` 关系，最终以发布后 count-only checker 输出为准。

发布前后均运行：

```bash
python scripts/ops/check_sidebar_questionnaire_access.py \
  --phase preflight \
  --expected-release-sha "$RELEASE_SHA"

python scripts/ops/check_sidebar_questionnaire_access.py \
  --phase post-deploy \
  --expected-release-sha "$RELEASE_SHA"
```

输出固定为 count/status/digest，`pii_included=false`。非空重复 questionnaire result token group 会令检查失败；历史 missing token 与 blocked legacy-only relation 只计数，不被恢复为可访问路径。

## 验证矩阵

| 场景 | 结果 |
| --- | --- |
| 合法 viewer + customer + session + current relation | 正常读写 |
| forged owner/actor | 403，无 PII |
| 跨员工、跨客户、跨 corp | 403，无 PII |
| token tamper、purpose mismatch、过期 | 401/403，无 PII |
| token 在新 OAuth session 重放 | 403，无 PII |
| follow relation 在签发后撤销 | write 前重查并 403 |
| result 顺序 submission id | 403 |
| result URL 复制到另一浏览器 | 403 |
| result grant tamper/过期 | 403 |
| 合法提交浏览器 | 200，主要 response contract 不变 |
| 合法后台管理员 | 走 admin result/submission route |

关键测试：

```bash
python -m pytest -q \
  tests/test_sidebar_owner_context_security.py \
  tests/test_sidebar_access_postgres.py \
  tests/test_route_policy_enforcement.py \
  tests/test_sidebar_v2_api.py \
  tests/test_sidebar_write_commands.py \
  tests/test_customer_read_model_request_scope.py \
  tests/test_questionnaire_h5_submit_commands.py \
  tests/test_questionnaire_result_access.py
```

## 发布、观测与回滚

- 发布：先等待 PR 全检查；合并后等待 main CI；测试机 health 必须返回 main merge exact SHA。
- smoke：验证合法 sidebar 自动 OAuth、合法读写、forged/cross-customer 403、同浏览器 result 200、复制链接 403。
- 日志与证据只记录状态、错误码、计数、digest、release SHA；禁止记录 unionid、external_userid、mobile、tag 或 answer 原值。
- 回滚：回滚到上一精确 release SHA。本批次无 schema migration；不得通过恢复 readonly、request owner 或 token-less result 止血。
