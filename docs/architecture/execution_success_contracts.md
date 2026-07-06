# Execution Success Contracts

This document defines the runtime contract for externally visible side effects.
Local projection can make an admin view current before an external adapter runs,
but it is not the same thing as external execution success.

## Status Vocabulary

| Status | Contract |
| --- | --- |
| `planned` | Intent is recorded and must not be dispatched until an operator or policy approval queues it. |
| `queued` | The job is eligible for the worker when schedule and retry gates are due. |
| `dispatching` | A worker has acquired the job. Stale `dispatching` jobs are reclaimed to `queued`. |
| `succeeded` | The responsible adapter returned success for the real external side effect or an explicitly record-only historical completion. |
| `failed_retryable` | The adapter reached a retryable error and `next_retry_at` controls the next attempt. |
| `failed_terminal` | The adapter or execution gate determined that retry will not succeed without operator or config change. |
| `blocked` | Policy, approval, or safety configuration prevented execution before the external side effect. |

## Capability Contracts

| Capability | Success means | Queue/blocked notes |
| --- | --- | --- |
| Questionnaire tags | `wecom.contact.tag.mark` or `wecom.contact.tag.unmark` succeeds against WeCom. Local `contact_tags` projection may update earlier for visibility. | Questionnaire submit must not call WeCom inline. Missing `external_userid` blocks only the external effect, not local projection. |
| Direct private send | The WeCom private-message adapter returns success for the exact target. | Sender comes from payload or `AICRM_WECOM_DEFAULT_SENDER_USERID`; execution mode and enabled effect types must allow private send. |
| Welcome message | `send_welcome_msg` succeeds for the captured welcome code. | Fallback private-message jobs have their own private-send contract. |
| Webhook push | The target webhook returns a 2xx response through External Effect Queue. | Legacy questionnaire sync push is retired; questionnaire external push is queue-only. |
| Payment refund | The provider refund request succeeds and the local order/refund mirror is updated from that response. | Missing provider transaction data is terminal until corrected. |
| Media upload | A real media/upload adapter must return remote success. Fixture or staging storage success is not production media success. |

## Approval Contract

Jobs created with `requires_approval=true` start as `planned`. Approval moves the
job to `queued` so the worker can pick it up. The worker only scans `queued` and
`failed_retryable` jobs, plus stale `dispatching` jobs that can be reclaimed.
