# R14-B Exact-SHA Deployment Rollback

## Goal

Restore the previously verified application release and runtime units whenever an uncommitted deployment fails.

## Implementation

1. Track when the checkout has switched and when all local/public verification has committed the release.
2. On failure before commit, stop any new-release units, reset to `before_sha`, restore `.release-sha`, and reinstall the old hashed lock when needed.
3. Start the previous Web release and require its health response header to match `before_sha` before restoring worker/timer units.
4. Keep the database at the forward migration head; migrations remain expand/contract compatible and are not automatically downgraded.
5. Extend deploy workflow contract tests for failure and success ordering.

## Verification

- Deploy workflow contract tests.
- CI workflow tests.
- Full architecture gates.
