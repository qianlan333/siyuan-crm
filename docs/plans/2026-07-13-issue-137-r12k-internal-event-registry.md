# R12-K Internal Event Registry App Lifecycle

## Goal

Move the mutable internal-event consumer registry out of `create_app` process-global mutation and into an app-owned composition boundary without changing event or worker behavior.

## Implementation

1. Add a package-root composition factory that builds and registers the complete consumer set into a fresh registry.
2. Store that registry on each FastAPI app and bind it for the duration of each request through a context-local registry scope.
3. Make default internal-event services, workers, and relays resolve the context-local registry, falling back to the explicit process registry used by CLI workers.
4. Add multi-app isolation, request binding, CLI fallback, and CI selector coverage.

## Verification

- Internal-event registry and worker tests.
- Multi-app composition tests.
- Permanent Full CI selector regression.
- Full architecture gates.
