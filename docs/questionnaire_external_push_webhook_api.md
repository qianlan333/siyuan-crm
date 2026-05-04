# 问卷外推 Webhook API 文档

适用对象：接收我方问卷提交外推消息的第三方系统  
文档范围：仅描述“单问卷外推”这条 webhook 链路，不包含 CRM 内部使用的其他 webhook  
最后校对：2026-04-06

## 1. 接口用途

当用户成功提交问卷后，我方 CRM 会把该次提交按固定 JSON 结构 `POST` 到你方提供的 webhook 地址。

这条链路的目标是：

- 让你方系统实时收到问卷提交结果
- 以问卷标题、提交时间、题目答案为基础做后续处理
- 不影响问卷主提交流程稳定性

要点：

- 问卷提交成功，不等于 webhook 投递成功
- 即使 webhook 失败，用户端问卷提交仍然会显示成功
- 当前版本没有自动重试；失败后由我方后台人工补发

## 2. 触发时机

我方在下面这个时点触发外推：

1. 用户提交问卷
2. 我方完成问卷校验
3. 我方把提交记录落库成功
4. 我方同步调用你方 webhook

因此你方收到 webhook 时，可以认为：

- 这份问卷提交已经被我方系统接收并保存
- webhook 只是“提交后的通知”，不是“提交是否成功”的判断依据

## 3. 你方需要提供什么

你方只需要提供一个可公网访问的完整 URL，例如：

```text
https://example.com/webhooks/questionnaire
```

建议：

- 使用 HTTPS
- 使用专用路径，不要和其他 webhook 共用
- 如果你方当前必须做简单鉴权，建议直接把密钥放进路径或查询串，例如：

```text
https://example.com/webhooks/questionnaire?token=your-secret-token
```

原因：当前版本我方不会额外发送 `Authorization` 头，也不会发送签名头。

## 4. HTTP 请求定义

### 4.1 请求方法

`POST`

### 4.2 请求头

当前实现里，唯一可以作为协议依赖的请求头是：

```http
Content-Type: application/json
```

说明：

- 当前不发送 Bearer Token
- 当前不发送签名头
- 当前不发送版本头

## 5. 请求体结构

### 5.1 顶层 JSON

```json
{
  "user_id": "union-external-push-success-001",
  "questionnaire_title": "来访测评",
  "submitted_at": "2026-04-06T18:21:10+08:00",
  "phone_number": "13800138012",
  "day": 20,
  "frequency": 20,
  "remark": "黄小璨 499 用户激活",
  "source_name": "黄小璨激活",
  "answers": [
    {
      "title": "你的预算",
      "answer": "10-30万"
    },
    {
      "title": "你的关注点",
      "answer": ["效果"]
    },
    {
      "title": "补充说明",
      "answer": ""
    },
    {
      "title": "手机号",
      "answer": "13800138012"
    }
  ]
}
```

### 5.2 字段说明

| 字段 | 类型 | 必有 | 说明 |
| --- | --- | --- | --- |
| `user_id` | `string` | 是 | 用户标识。当前实现取提交记录里的 `respondent_key` 优先值，因此通常等于 `unionid` / `openid` / `external_userid` 之一；若这些都没有，可能退化为系统生成的匿名键。你方不能假设它一定是企业微信用户 ID。 |
| `questionnaire_title` | `string` | 是 | 问卷标题。 |
| `submitted_at` | `string` | 是 | 提交时间，ISO 8601 字符串，例如 `2026-04-06T18:21:10+08:00`。 |
| `phone_number` | `string` | 是 | 若问卷里存在手机号题且用户提交了该值，这里发送该手机号；若问卷没有手机号题，或该字段最终没有值，则固定发送字符串 `"NULL"`。 |
| `day` | `number` | 否 | 后台为当前问卷手动配置的固定数字字段。未配置时不发送。 |
| `frequency` | `number` | 否 | 后台为当前问卷手动配置的固定数字字段。未配置时不发送。 |
| `remark` | `string` | 否 | 后台为当前问卷手动配置的固定文本字段。未配置时不发送。 |
| 其他自定义字段 | `string` | 否 | 后台手动新增的自定义顶层参数，按“参数名: 参数值”直接平铺到顶层 JSON。若参数名重复或命中保留字段，后台保存会报错。 |
| `answers` | `array<object>` | 是 | 问卷答案数组。 |

### 5.3 `answers[]` 元素说明

| 字段 | 类型 | 必有 | 说明 |
| --- | --- | --- | --- |
| `title` | `string` | 是 | 题目标题快照。 |
| `answer` | `string` 或 `array<string>` | 是 | 题目答案。不同题型返回不同结构，见下表。 |

### 5.4 `answer` 字段的类型规则

| 题型 | `answer` 结构 | 示例 |
| --- | --- | --- |
| 单选题 `single_choice` | `string` | `"10-30万"` |
| 多选题 `multi_choice` | `array<string>` | `["效果", "价格"]` |
| 文本题 `textarea` | `string` | `"希望尽快联系我"` |
| 手机号题 `mobile` | `string` | `"13800138012"` |

补充说明：

- 单选题未选中时，当前会发空字符串 `""`
- 多选题未选中时，当前会发空数组 `[]`
- 文本题未填写时，当前会发空字符串 `""`
- 手机号题未填写时，若该题是必填，提交本身不会成功，因此正常不会出现无值成功提交
- 自定义顶层参数当前统一按字符串发送

## 6. 当前不会发送的字段

为避免对方误解，下面这些字段 **当前版本不会出现在 webhook 请求体里**：

- `questionnaire_id`
- `questionnaire_slug`
- `submission_id`
- `openid`
- `unionid`
- `external_userid`
- `follow_user_userid`
- 总分 `total_score`
- 标签 `final_tags`
- 题目 ID / 选项 ID

如果你方必须依赖这些字段，需要我们单独升级协议。

## 7. 成功与失败判定规则

这是对接里最重要的部分。

### 7.1 我方如何判定成功

当前版本里，我方只在下面这个条件成立时判定 webhook 成功：

- **HTTP 状态码必须等于 `200`**

注意：

- `201` 不算成功
- `202` 不算成功
- `204` 不算成功
- 任何 `4xx` / `5xx` 都算失败

### 7.2 我方会不会解析你方返回体

**不会。**

当前实现里，我方不会根据你方响应体里的业务字段做判断。

例如下面这个响应：

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"success": false, "message": "业务未受理"}
```

在当前版本里，**仍然会被我方记为成功**，因为状态码是 `200`。

因此请记住：

- 如果你方希望我方认为“成功”，请返回 `200`
- 如果你方希望我方认为“失败”，请返回非 `200`

## 8. 推荐响应格式

虽然我方当前不解析响应体，但为了联调和排查方便，建议你方统一返回 JSON。

### 8.1 推荐成功响应

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ok": true,
  "message": "accepted"
}
```

### 8.2 推荐参数错误响应

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "ok": false,
  "error": "invalid_payload",
  "message": "mobile is required"
}
```

### 8.3 推荐服务繁忙响应

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{
  "ok": false,
  "error": "service_unavailable",
  "message": "please retry later"
}
```

## 9. 不同返回情况下，我方会怎样处理

| 你方返回情况 | 我方记录结果 | 是否影响用户问卷提交成功 | 后续是否可能再次发送 |
| --- | --- | --- | --- |
| `200 OK` | `success` | 不影响，用户提交成功 | 正常不会自动重发 |
| 非 `200`，例如 `400/401/403/404/429/500/502/503` | `failed` | 不影响，用户提交成功 | 可能由我方后台人工补发 |
| 超过超时未返回 | `failed`，原因 `request timeout` | 不影响，用户提交成功 | 可能由我方后台人工补发 |
| 网络错误、DNS 错误、TLS 错误 | `failed`，原因类似 `network error: ...` | 不影响，用户提交成功 | 可能由我方后台人工补发 |
| 我方全局关闭外推 | `skipped` | 不影响，用户提交成功 | 本次不会发送 |

## 10. 超时要求

当前版本默认超时是 **3 秒**。

配置规则：

- 默认值：`3` 秒
- 最小值：`0.5` 秒
- 最大值：`10` 秒

因此你方接收端应按下面口径设计：

- 尽量在 `3` 秒内返回
- 最好收到后先快速落队列/落库，再立即返回 `200`
- 不要在 webhook 请求里做长耗时同步处理

推荐模式：

1. 接收请求
2. 基础校验
3. 写入你方队列/数据库
4. 立即返回 `200`
5. 后续异步慢处理

## 11. 重试与重复投递

当前版本口径：

- **没有自动重试**
- **没有定时重试**
- **没有消息队列**
- webhook 失败后，只能由我方后台人工补发

这意味着你方需要按“至少一次投递”设计，而不是“最多一次”。

### 11.1 为什么会出现重复投递

重复投递可能来自：

- 第一次你方返回非 `200`
- 第一次超时
- 网络抖动
- 我方人工执行补发

### 11.2 幂等建议

当前 payload 里没有独立的 `submission_id` 或 `event_id`，所以你方如果要做去重，建议使用下面这个组合键：

```text
questionnaire_title + user_id + submitted_at
```

说明：

- 这是基于当前协议结构给出的**工程建议**
- 它不是我方显式承诺的“全局唯一事件 ID”
- 如果你方需要强幂等主键，建议我们后续补一个 `submission_id`

## 12. 安全说明

当前版本的安全边界如下：

- 不带 Bearer Token
- 不带签名
- 不带时间戳签名头
- 不做双向 TLS

因此如果你方必须做接入保护，建议至少采用以下任一方案：

1. 使用带随机 secret 的专用路径  
   例如：`/webhooks/questionnaire/4f2f0f6c9d3e`

2. 在查询串里带固定 token  
   例如：`/webhooks/questionnaire?token=your-secret-token`

3. 由你方网关做来源 IP 白名单  
   这条建议需要和我方部署侧单独确认出口 IP

## 13. 联调样例

你方可以用下面这条 `curl` 在本地先模拟我方请求：

```bash
curl -X POST 'https://your-domain.example.com/webhooks/questionnaire' \
  -H 'Content-Type: application/json' \
  --data '{
    "user_id": "union-external-push-success-001",
    "questionnaire_title": "来访测评",
    "submitted_at": "2026-04-06T18:21:10+08:00",
    "answers": [
      {"title": "你的预算", "answer": "10-30万"},
      {"title": "你的关注点", "answer": ["效果"]},
      {"title": "补充说明", "answer": ""},
      {"title": "手机号", "answer": "13800138012"}
    ]
  }'
```

建议你方至少验证这 4 类返回：

1. 返回 `200`
2. 返回 `400`
3. 返回 `500`
4. 故意延迟超过 `3` 秒

## 14. 接收方验收清单

- 能接收 `POST application/json`
- 能正确解析 `answers[].answer` 的动态类型
- 能在 `3` 秒内返回
- 成功时固定返回 `200`
- 失败时明确返回非 `200`
- 具备基本日志，至少能查：
  - 接收时间
  - `user_id`
  - `questionnaire_title`
  - `submitted_at`
- 具备幂等处理能力

## 15. 当前协议边界总结

一句话总结当前版本：

- 我方向你方发送固定 JSON
- 你方只要返回 `200`，我方就认为成功
- 非 `200` / 超时 / 网络错误都记失败
- 失败不会影响用户提交成功
- 当前没有自动重试，只有人工补发
- 当前没有签名，没有事件唯一 ID

如果你方需要下面任一能力，需要单独升级协议：

- Bearer Token
- HMAC 签名
- 固定版本头
- 独立 `submission_id`
- 独立 `event_id`
- 自动重试回调约定
