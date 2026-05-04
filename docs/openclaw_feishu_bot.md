# OpenClaw Feishu Bot

## Goal

This adds an independent Feishu app bot service so Feishu can act as the
conversation entry between you and OpenClaw.

The bot does not change CRM service code.

It calls existing OpenClaw-side capabilities:

- `get_customer_chat_context`
- `customer_chat_context_preflight`

## Runtime Shape

Independent service:

- `openclaw_service.feishu.app`
- `openclaw_service.feishu.longconn`

CLI runner:

```bash
python -m openclaw_service.cli.feishu_bot --host 0.0.0.0 --port 5060
```

Long connection runner:

```bash
python -m openclaw_service.cli.feishu_longconn_bot
```

Webhook endpoints:

- `GET /health`
- `POST /feishu/events`

If the Feishu app is configured for long connection, use the long connection
runner instead of webhook callbacks. In that mode, no public callback URL is
required.

## Supported Commands

In Feishu chat:

- `/context <external_userid>`
- `/preflight <external_userid>`
- `/help`

You can also send a bare `wm_xxx` and it will be treated as a context query.

## Internal Call Path

Feishu event callback or long connection event
-> command parser
-> existing OpenClaw registry / preflight
-> CRM-backed context chain

Specifically:

- `/context`
  - `call_tool_by_name("get_customer_chat_context", {...})`

- `/preflight`
  - `run_customer_chat_context_preflight(...)`

## Required Environment

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`

Recommended:

- `FEISHU_VERIFICATION_TOKEN`

Also required for the CRM side:

- `CRM_API_BASE_URL`
- `CRM_API_TOKEN`

## What You Need To Fill In Feishu Console

Webhook mode:

1. Event subscription request URL
   - `https://<your-domain>/feishu/events`

2. Verification token
   - set the same value into `FEISHU_VERIFICATION_TOKEN`

3. Message event subscription
   - enable receiving text messages for the bot

Long connection mode:

- select `使用长连接接收事件`
- enable `im.message.receive_v1`
- no public request URL is needed

This implementation assumes plaintext text message handling and does not add
event encryption handling in this round.

## What This Does Not Do

- does not generate suggestions
- does not modify CRM service code
- does not access CRM database directly
- does not add full conversation orchestration
