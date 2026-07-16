# AI Audience Scheduler

`scripts/run_ai_audience_scheduler.py` is the system scheduler for AI audience packages.

It follows the queue boundaries:

- emits `ai_audience.refresh.incremental_tick` every scheduler run;
- emits `ai_audience.refresh.daily_tick` only during the configured daily window, default `Asia/Shanghai 02:00`;
- dispatches AI audience internal-event consumers for source poke, refresh, and member-event outbound planning;
- runs with `AICRM_INTERNAL_EVENT_RELAY_ROLE=consumer_only` and therefore cannot acquire or relay global outbox rows;
- never sends webhook or WeCom messages directly.

External side effects remain in `external_effect_job` and are executed only by the External Effect worker.

## Production Timer

Install the dedicated timer alongside the existing internal-event and external-effect workers:

```bash
sudo cp deploy/openclaw-ai-audience-scheduler.service /etc/systemd/system/
sudo cp deploy/openclaw-ai-audience-scheduler.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-ai-audience-scheduler.timer
```

The timer runs every 3 minutes:

```text
OnCalendar=*-*-* *:0/3:00
```

The service sets a pair allowlist for AI audience consumers only, so it does not execute unrelated internal-event consumers. The pair allowlist is an execution filter, not a relay ownership mechanism: relay is structurally disabled in this scheduler and remains owned only by `scripts/run_internal_event_worker.py`.
