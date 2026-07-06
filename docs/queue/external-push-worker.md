# External Push Worker

`scripts/run_external_push_worker.py` is the Next-native system runner for product-payment external webhooks. Payment success enqueues `transaction.paid` into `domain_event_outbox`; this worker turns due outbox rows into `external_push_delivery` attempts and retries failed deliveries on their scheduled retry time.

## Runtime Contract

- Payment notification path: marks the order paid and enqueues one idempotent `transaction.paid` outbox row.
- External push worker: scans due `domain_event_outbox` rows and due `external_push_delivery` retries through `aicrm_next.external_push`.
- Webhook payload: `transaction.paid` sends a questionnaire-compatible JSON body with top-level `phone_number`, `type`, `day`, `frequency`, `remark`, `submitted_at`, `questionnaire_title`, `delivery_id`, `event`, `order`, and `product`.
- Delivery log: every attempted webhook POST is recorded in `external_push_delivery`.
- Delivery privacy: stored delivery request bodies keep sensitive fields redacted even when the outbound webhook payload contains the full `phone_number`.
- Idempotency: one order/config/event combination creates at most one delivery row.

The payment request must not synchronously block on the external receiver. The worker is the only production path that sends product-payment external webhooks, and it does not require Flask app context.

## Configuration

The worker reads the same production env file as the app:

```bash
/home/ubuntu/.openclaw-wecom-pg.env
```

Optional batch size:

```bash
EXTERNAL_PUSH_WORKER_BATCH_SIZE=50
```

## systemd

Install and enable the worker timer with the app deployment:

```bash
sudo cp deploy/openclaw-external-push-worker.service /etc/systemd/system/
sudo cp deploy/openclaw-external-push-worker.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable openclaw-external-push-worker.timer
sudo systemctl restart openclaw-external-push-worker.timer
sudo systemctl start openclaw-external-push-worker.service
sudo systemctl status openclaw-external-push-worker.timer --no-pager
```

The timer runs every minute at second 20. The one-shot start drains any backlog immediately after deployment.

## Verification

For a paid order:

1. Confirm `/api/h5/wechat-pay/notify` returned 200.
2. Confirm the order is `paid`.
3. Check the worker:

```bash
sudo journalctl -u openclaw-external-push-worker.service -n 100 --no-pager
sudo systemctl status openclaw-external-push-worker.timer --no-pager
```

4. Confirm `/api/admin/wechat-pay/orders/<order_id>/external-push-deliveries` has a delivery row with `response_status` and `status`.
