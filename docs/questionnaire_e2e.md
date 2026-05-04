# 问卷模块联调清单

## 1. 配置公众号 OAuth

在启动服务前设置下面 4 个环境变量：

```bash
export SECRET_KEY='replace-with-a-long-random-string'
export WECHAT_MP_APP_ID='wx_your_app_id'
export WECHAT_MP_APP_SECRET='your_mp_app_secret'
export WECHAT_MP_OAUTH_SCOPE='snsapi_base'
```

如果你本地还要同时跑企微打标签链路，也一起配置：

```bash
export WECOM_CORP_ID='ww_your_corp_id'
export WECOM_CONTACT_SECRET='your_wecom_contact_secret'
export WECOM_SECRET='your_wecom_secret'
export WECOM_AGENT_ID='1000002'
export WECOM_DEFAULT_OWNER_USERID='sales_01'
```

## 2. 配置网页授权域名

在公众号后台把服务域名加入网页授权域名。

例如你的问卷地址最终会是：

```text
https://your-domain.com/s/<slug>
```

则网页授权域名应配置为：

```text
your-domain.com
```

如果你使用测试环境内网穿透，也要把穿透后的域名配置进去。

## 3. 启动服务

```bash
cd <repo-root>
python3 app.py init-db
python3 app.py run
```

启动后先看日志里是否出现：

```text
questionnaire oauth config: WECHAT_MP_APP_ID=set/missing, WECHAT_MP_APP_SECRET=set/missing, WECHAT_MP_OAUTH_SCOPE=set/missing, SECRET_KEY=set/missing
```

如果缺项，服务仍会启动，但微信 OAuth 不会生效。

## 4. 创建一个测试问卷

```bash
curl -X POST http://127.0.0.1:5000/api/admin/questionnaires \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"线索打标签测试问卷",
    "title":"来访测评",
    "description":"请完成以下问题。",
    "redirect_url":"",
    "questions":[
      {
        "type":"single_choice",
        "title":"预算范围",
        "required":true,
        "options":[
          {"option_text":"10万以内","score":1,"tag_codes":["tag_low_budget"],"sort_order":1},
          {"option_text":"10-30万","score":3,"tag_codes":["tag_mid_budget"],"sort_order":2}
        ]
      },
      {
        "type":"multi_choice",
        "title":"关注点",
        "required":true,
        "options":[
          {"option_text":"效果","score":2,"tag_codes":["tag_focus_result"],"sort_order":1},
          {"option_text":"服务","score":1,"tag_codes":["tag_focus_service"],"sort_order":2}
        ]
      },
      {
        "type":"textarea",
        "title":"补充说明",
        "required":false
      }
    ],
    "score_rules":[
      {"min_score":4,"max_score":99,"tag_codes":["tag_high_intent"],"sort_order":1}
    ]
  }'
```

返回结果里会包含：

- `questionnaire.slug`
- `questionnaire.public_url`

也可以直接打开后台页面：

```text
http://127.0.0.1:5000/admin/questionnaires/ui
```

## 5. 在微信中打开 /s/<slug>

把刚创建出来的问卷链接发到微信里打开：

```text
https://your-domain.com/s/<slug>?source_channel=wechat&campaign_id=cmp-001&staff_id=sales_01
```

如果配置了公众号 OAuth，微信内打开会自动跳：

```text
/s/<slug> -> /api/h5/wechat/oauth/start -> 微信授权 -> /api/h5/wechat/oauth/callback -> /s/<slug>
```

## 6. 验证 session 已写入 openid/unionid

测试环境下，接口默认开放：

```bash
curl http://127.0.0.1:5000/api/debug/questionnaire/session
```

返回里至少会有：

```json
{
  "ok": true,
  "questionnaire_h5_identity": {
    "respondent_key": "...",
    "openid": "...",
    "unionid": "...",
    "oauth_at": "...",
    "slug": "..."
  }
}
```

如果线上要临时启用该接口：

```bash
export ENABLE_DEBUG_QUESTIONNAIRE_SESSION_API=1
```

## 7. 验证 submission 已命中 identity_map

提交问卷后查询：

```bash
sqlite3 <repo-root>/data.sqlite3 "
select id, identity_map_id, respondent_key, openid, unionid, external_userid, follow_user_userid, matched_by
from questionnaire_submissions
order by id desc
limit 5;"
```

关注这几列：

- `identity_map_id` 不为空
- `external_userid` 不为空
- `matched_by` 为 `unionid` / `openid` / `external_userid`

## 8. 验证 openid 被回填

如果最初是用 `unionid` 命中，而历史 `identity_map.openid` 为空，则提交后会自动回填。

```bash
sqlite3 <repo-root>/data.sqlite3 "
select id, external_userid, unionid, openid, follow_user_userid
from wecom_external_contact_identity_map
where unionid='union-001';"
```

检查 `openid` 是否已经从空值变成最新授权拿到的 openid。

## 9. 验证标签已写回 SCRM

先看问卷提交计算出来的最终标签：

```bash
sqlite3 <repo-root>/data.sqlite3 "
select id, final_tags
from questionnaire_submissions
order by id desc
limit 5;"
```

再看本地标签快照：

```bash
sqlite3 <repo-root>/data.sqlite3 "
select external_userid, userid, tag_id, created_at
from contact_tags
order by id desc
limit 20;"
```

最后看 SCRM 写回审计表：

```bash
sqlite3 <repo-root>/data.sqlite3 "
select submission_id, external_userid, follow_user_userid, final_tags, status, error_message, created_at
from questionnaire_scrm_apply_logs
order by id desc
limit 20;"
```

判断规则：

- `status=success`：已成功调用 SCRM 打标
- `status=skipped`：因 identity 或标签缺失跳过
- `status=failed`：已尝试调用，但 SCRM 返回失败
