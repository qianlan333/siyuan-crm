# CRM Assistant Troubleshooting

## Campaign Allocated Zero Members

Preview each segment, check overlap/priority, and confirm the SQL returns
`member_id`.

## Segment SQL Fails

Run validation first. Use only allowlisted audience tables and remove
destructive keywords.

## Approval Token Fails

Ask the operator to generate a fresh CRM approval token for the exact campaign
or broadcast being started.

## Campaign Stops Moving

Check whether it is paused, whether `next_due_at` is in the future, and whether
the scheduler is running.

## Too Many Touches

Review recent outcomes and frequency-budget blockers. Do not work around
do-not-disturb or budget protections.

## Need To Stop A Mistake

Pause the campaign immediately, tell the operator which ids were affected, and
use recent-outcome queries for the follow-up audit.
