# Production Diagnostic Sandbox Notes

This repo does not publish concrete production connection details, dispatcher
paths, host aliases, or command cookbooks. Keep those in the private ops handoff
for the current environment.

Any production diagnostic extension must keep this contract:

- read-only / dry-run by default
- no shell passthrough
- no arbitrary script argument
- no write-capable bridge
- no external effect execution unless separately approved
- no production migration
- no token, secret, raw receiver, raw external user id, phone, raw target list,
  raw message body, or raw callback body output

Diagnostic statuses such as skipped write validation or permission-limited reads
are observability signals, not execution success claims.
