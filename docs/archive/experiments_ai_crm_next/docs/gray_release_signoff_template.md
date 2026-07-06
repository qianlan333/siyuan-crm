# Gray Release Signoff Template

Use one copy of this template per batch execution. Do not reuse signoff across modules.

## Batch

- batch name:
- included routes:
- excluded routes confirmed:
- operator:
- timestamp:
- git commit:
- old service version:
- next service version:
- database target:
- external adapters mode:
  - WeCom:
  - OAuth:
  - payment:
  - OpenClaw:
  - cloud storage:

## Evidence

- ordinary pytest result:
- six parity result:
- selected smoke result:
- readonly dual-run result, if applicable:
- frontend screenshot baseline link:
- generated gray release report:
- side-effect safety:
- known legacy drift:
- skipped routes and reasons:

## Risk Acceptance

- accepted risks:
- rejected risks:
- production data impact:
- external side-effect impact:
- rollback owner:
- rollback command reviewed:
- rollback verification command:

## Decision

- go/no-go decision:
- decision reason:
- approver:
- signoff:
- post-release monitoring owner:
- rollback window:
