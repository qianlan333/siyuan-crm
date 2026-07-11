# 群运营通用群发 API

## 用途

该接口供受信任的自动化执行器直接完成客户群群发，不依赖后台登录 session、CSRF cookie 或 SSH。接口支持：

- 纯文本；
- 直接上传 1 至 3 张图片；
- 日课小程序卡片；
- 文本、图片和卡片的任意组合。

生产地址：

```text
POST https://www.youcangogogo.com/api/automation/group-ops/broadcast
```

## 鉴权与幂等

```http
Authorization: Bearer <AUTOMATION_INTERNAL_API_TOKEN>
Idempotency-Key: <本次业务唯一值>
```

服务端使用常量时间比较验证 Bearer token。`Idempotency-Key` 必填；同一 key 重放不会重新上传素材或再次群发，而是返回原任务状态。

## JSON 请求

适用于纯文本、日课卡片或已经持有企微 `media_id` 的图片：

```json
{
  "text": "今天的内容已更新",
  "card_path": "pages/article/article?lesson_id=2fe19357-3b07-4547-9a3f-c14696cc81f5&from=learn",
  "card_title": "可选卡片标题",
  "image_media_ids": []
}
```

`text` 也可写成 `recommendation_text`。如果未传 `card_title`，服务端优先提取文案中的 `《标题》`，否则使用默认标题。

纯文本示例：

```bash
curl -X POST 'https://www.youcangogogo.com/api/automation/group-ops/broadcast' \
  -H 'Authorization: Bearer <TOKEN>' \
  -H 'Idempotency-Key: daily-text-20260710-001' \
  -H 'Content-Type: application/json' \
  --data '{"text":"今天的群发话术"}'
```

## Multipart 图片请求

图片文件使用重复的 `images` 字段。每张图片不超过 10 MB，最多 3 张，仅接受 PNG、JPEG、GIF、WebP，并校验文件内容签名。

```bash
curl -X POST 'https://www.youcangogogo.com/api/automation/group-ops/broadcast' \
  -H 'Authorization: Bearer <TOKEN>' \
  -H 'Idempotency-Key: daily-image-20260710-001' \
  -F 'text=图片说明文字' \
  -F 'images=@/path/to/image-1.png' \
  -F 'images=@/path/to/image-2.jpg'
```

Multipart 同样支持 `recommendation_text`、`card_path`、`card_title` 和重复的 `image_media_ids` 字段。

## 成功响应

```json
{
  "ok": true,
  "status": "succeeded",
  "duplicate": false,
  "event_id": 37,
  "external_effect_job_id": 1010,
  "attempt_status": "succeeded",
  "error_code": "",
  "error_message": "",
  "requested_chat_count": 10,
  "exact_target_verified": true,
  "wecom_msgid_present": true,
  "real_external_call_executed": true,
  "wecom_send_executed": true,
  "content": {
    "text_present": true,
    "image_count": 0,
    "uploaded_image_count": 0,
    "card_attached": true,
    "card_title": "卡片标题"
  },
  "route_owner": "ai_crm_next"
}
```

只有队列任务达到 `succeeded` 且企微返回精确目标校验通过时，`ok` 才为 `true`。

## 安全边界

- 不开放或绕过任何 `/api/admin/*` 登录鉴权；
- 不接受任意远程图片 URL；日课封面只从固定的 `ip.lhbl.com.cn` 地址生成；
- 不返回 token、企微 `media_id`、群聊 ID 或原始第三方响应；
- 服务端实时读取配置的群运营计划和绑定群，不接受调用方指定目标群；
- 测试必须使用 fake adapter，不访问真实企微或日课封面服务。
