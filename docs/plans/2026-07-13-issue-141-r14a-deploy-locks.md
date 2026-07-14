# R14-A Deployment Serialization

## Goal

Prevent concurrent test or production deployments from entering the migration and restart critical section.

## Implementation

1. Serialize the reusable deploy workflow by target environment with cancellation disabled.
2. Serialize manual production promotions independently from the called deploy workflow.
3. Acquire a target-specific server `flock` before inspecting the current checkout and hold it for the complete SSH deployment session.
4. Extend deploy workflow contract tests and keep deployment changes on mandatory Full CI.

## Verification

- Deploy workflow contract tests.
- CI selector regression.
- Full architecture gates.
