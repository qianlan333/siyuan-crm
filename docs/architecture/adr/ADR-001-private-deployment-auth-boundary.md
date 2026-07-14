# ADR-001: Private-deployment authentication boundary

- Status: Accepted
- Date: 2026-07-12
- Owner: `platform_foundation.auth_platform`
- Decision scope: AI-CRM-owned authentication and authorization only

## Context

AI-CRM is a single-tenant private deployment. It must remove shared bearer
environment variables, URL credentials, route-local comparisons and fallback
validators without introducing an independent identity platform or a public
authorization-server product.

Human operators already enter through enterprise WeCom. Internal workers,
scripts and API agents need separate, revocable identities. AI-CRM-owned
webhooks need one deterministic raw-body signing contract, while supplier
callbacks must continue to use each supplier's official protocol.

## Decision

Human login uses WeCom OAuth as its only upstream. On successful callback,
AI-CRM issues a random server-side session and keeps RBAC, `session_version`,
CSRF and action-token enforcement inside the application.

Every machine caller has an independent `client_id` and high-entropy
`client_secret`. Only a scrypt verifier is stored. A TLS-protected
`client_credentials` request issues an HS256 JWT with a default lifetime of 30
minutes and no refresh credential. The required claims are `iss`, `aud`, `sub`,
`client_id`, `scope`, `iat`, `exp`, `jti` and `auth_version`. Resource servers
verify the JWT locally, then confirm the client remains enabled and that its
current `auth_version` matches through a short-lived registry cache.

Workers and timers in the application process call application services
directly with a controlled `AuthContext`. Separate processes and CLI tools use
the same client-credential JWT boundary as other API clients.

AI-CRM-owned inbound and outbound webhooks use HMAC-SHA256 over:

```text
timestamp + "\n" + event_id + "\n" + raw_body
```

The receiver enforces a five-minute window, bounded future clock skew,
registered client capability, optional source CIDR and persistent event replay
protection. Webhook secrets are stored only through Secret Store references.

The context delivered to business code contains only `principal_type`,
`principal_id`, `client_id`, `admin_user_id`, `corp_id`, capabilities/scopes,
`owner_scope`, `auth_version` and `request_id`.

## Security invariants

- Credentials never appear in query strings, path parameters, logs or database
  plaintext columns.
- A route is protected by the centralized route-policy middleware and exactly
  one declared authentication scheme.
- JWT signature, issuer, audience, expiry, client status, `auth_version`, scope,
  capability, owner scope and optional CIDR are all enforced.
- Disabling a client or rotating its secret increments `auth_version`, making
  already-issued JWTs unusable after the bounded registry-cache interval.
- Supplier-native callbacks remain outside the AI-CRM webhook HMAC contract.
- No legacy credential or permissive fallback survives the cutover.

## Explicit non-goals

- Independent authorization server, discovery, consent or browser PKCE flows.
- Refresh credentials, online token introspection or token exchange.
- Proof-of-possession, client certificates or financial-grade profiles.
- Multi-tenant or public developer-platform behavior.

## Consequences

The deployment must bootstrap all API and webhook client profiles before the
single cutover. Generated secrets are written once to the host Secret Store and
are never printed. Readiness checks compare registered profiles and runtime
references without exposing secret material. Rollback restores the prior
release as a unit; there is no dual-stack authentication period.
