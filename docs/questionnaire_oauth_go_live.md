# 问卷 OAuth 真实联调最短步骤

## 1. 配置环境变量

在服务启动前设置下面 4 个变量，只通过环境变量注入，不要把密钥写进代码：

```bash
export WECHAT_MP_APP_ID='你的公众号 AppID'
export WECHAT_MP_APP_SECRET='你的公众号 AppSecret'
export WECHAT_MP_OAUTH_SCOPE='snsapi_base'
export SECRET_KEY='请替换成固定且足够长的随机字符串'
```

如果还要联调 identity_map 命中和 SCRM 打标签，再补齐：

```bash
export WECOM_CORP_ID='你的企业微信 CorpID'
export WECOM_CONTACT_SECRET='你的企业微信通讯录 Secret'
export WECOM_SECRET='你的企业微信应用 Secret'
export WECOM_AGENT_ID='你的企业微信应用 AgentId'
export WECOM_DEFAULT_OWNER_USERID='sales_01'
```

## 2. 配置网页授权域名

在公众号后台把网页授权域名配置为：

```text
youcangogogo.com
```

如果你最终从 `https://youcangogogo.com/s/<slug>` 打开问卷，OAuth callback 会回到：

```text
https://youcangogogo.com/api/h5/wechat/oauth/callback
```

## 3. 启动服务并确认已读到配置

```bash
cd <repo-root>
python3 app.py init-db
python3 app.py run
```

启动后优先看日志里这两行：

```text
questionnaire oauth config: WECHAT_MP_APP_ID=set, WECHAT_MP_APP_SECRET=set, WECHAT_MP_OAUTH_SCOPE=set, SECRET_KEY=set
questionnaire session debug api: enabled/disabled
```

如果 `SECRET_KEY` 显示为 `missing`，说明当前仍在用默认开发占位值，真实 OAuth 不应上线。

## 4. 用 preflight 再确认一次

```bash
curl -s http://127.0.0.1:5000/api/admin/questionnaires/preflight | python3 -m json.tool
```

重点看：

- `wechat_oauth_configured=true`
- `wecom_contact_configured=true`
- `wecom_tags_api_available=true`
- `identity_map_available=true`

如果 `wechat_oauth_configured=false`，优先检查：

- `WECHAT_MP_APP_ID`
- `WECHAT_MP_APP_SECRET`
- `SECRET_KEY`

## 5. 创建一个测试问卷

```bash
curl -X POST http://127.0.0.1:5000/api/admin/questionnaires \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"公众号 OAuth 联调问卷",
    "title":"微信联调测试",
    "description":"请提交一份测试数据。",
    "redirect_url":"",
    "questions":[
      {
        "type":"single_choice",
        "title":"预算范围",
        "required":true,
        "options":[
          {"option_text":"10万以内","score":1,"tag_codes":["et_tag_low_budget"]},
          {"option_text":"10-30万","score":3,"tag_codes":["et_tag_mid_budget"]}
        ]
      },
      {
        "type":"multi_choice",
        "title":"关注点",
        "required":true,
        "options":[
          {"option_text":"效果","score":2,"tag_codes":["et_tag_focus_result"]},
          {"option_text":"服务","score":1,"tag_codes":["et_tag_focus_service"]}
        ]
      }
    ],
    "score_rules":[
      {"min_score":4,"max_score":99,"tag_codes":["et_tag_high_intent"]}
    ]
  }'
```

记下返回中的：

- `questionnaire.id`
- `questionnaire.slug`
- `questionnaire.public_url`

## 6. 在微信里打开问卷

把下面链接发到微信里打开：

```text
https://youcangogogo.com/s/<slug>?source_channel=wechat&campaign_id=cmp-oauth-001&staff_id=sales_01
```

正常链路应该是：

```text
/s/<slug>
-> /api/h5/wechat/oauth/start
-> 微信网页授权
-> /api/h5/wechat/oauth/callback
-> 302 回 /s/<slug>
```

## 7. 验证 session 已写入 openid / unionid

如果是测试环境，直接调用：

```bash
curl -s http://127.0.0.1:5000/api/debug/questionnaire/session | python3 -m json.tool
```

如果是线上临时排查，先开启：

```bash
export ENABLE_DEBUG_QUESTIONNAIRE_SESSION_API=1
```

然后确认返回里至少有：

- `respondent_key`
- `openid`
- `unionid`
- `oauth_at`
- `slug`

## 8. 提交问卷并验证命中 identity_map

提交后执行：

```bash
psql "$DATABASE_URL" <<'SQL'
select id, questionnaire_id, identity_map_id, respondent_key, openid, unionid, external_userid, follow_user_userid, matched_by, total_score, final_tags
from questionnaire_submissions
order by id desc
limit 5;
SQL
```

重点看：

- `identity_map_id` 不为空
- `external_userid` 不为空
- `follow_user_userid` 不为空
- `matched_by` 为 `unionid` / `openid`

## 9. 验证 openid 是否被回填

如果这次是通过 `unionid` 命中，且历史 `openid` 为空，再查：

```bash
psql "$DATABASE_URL" <<'SQL'
select id, external_userid, unionid, openid, follow_user_userid
from wecom_external_contact_identity_map
order by id desc
limit 20;
SQL
```

确认对应记录里的 `openid` 已经被写回。

## 10. 验证标签是否写回 SCRM

先查问卷提交结果：

```bash
psql "$DATABASE_URL" <<'SQL'
select id, final_tags, submitted_at
from questionnaire_submissions
order by id desc
limit 5;
SQL
```

再查 SCRM 写回审计：

```bash
psql "$DATABASE_URL" <<'SQL'
select submission_id, external_userid, follow_user_userid, final_tags, status, error_message, created_at
from questionnaire_scrm_apply_logs
order by id desc
limit 20;
SQL
```

最后查本地标签快照：

```bash
psql "$DATABASE_URL" <<'SQL'
select external_userid, userid, tag_id, created_at
from contact_tags
order by id desc
limit 20;
SQL
```

判断规则：

- `questionnaire_scrm_apply_logs.status=success`：已调用成功
- `questionnaire_scrm_apply_logs.status=skipped`：因 identity 或标签缺失跳过
- `questionnaire_scrm_apply_logs.status=failed`：已发起调用但企微接口失败

## 11. 失败时优先看这些日志

优先检查服务日志里这几类：

- `oauth start ...`
- `oauth callback success ...`
- `oauth callback failed ...`
- `oauth session written ...`
- `questionnaire identity resolved ...`
- `questionnaire submission saved ...`
- `questionnaire scrm applied ...`
- `questionnaire scrm skip ...`
- `questionnaire scrm apply failed ...`

排查顺序建议：

1. 先看是否出现 `oauth start ...`
2. 再看 `oauth callback success ...` 是否出现
3. 再查 debug session 里是否已写入 `openid/unionid`
4. 再查 `questionnaire_submissions` 是否命中 `identity_map_id`
5. 最后看 `questionnaire_scrm_apply_logs` 是 `success`、`skipped` 还是 `failed`
