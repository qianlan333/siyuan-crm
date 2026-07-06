#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
Production diagnostics are intentionally not exposed from this public repo entry.

Use the private ops handoff for the current environment. That private handoff
must keep diagnostics read-only / dry-run by default and must not expose host
aliases, dispatcher paths, command cookbooks, arbitrary SQL bridges, shell
passthrough, tokens, secrets, raw receiver data, raw external user ids, phone
numbers, target lists, message bodies, or callback bodies.
EOF

exit 2
