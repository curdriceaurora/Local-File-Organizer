# Plugin Security Guidance

## Threat Model for Local File Management

Plugins may receive user-provided paths and payloads. The primary risks are path traversal, unauthorized writes, and data exfiltration through webhook callbacks.

## Controls in This Implementation

- API endpoints route all filesystem paths through `resolve_path(...)` and allowed roots.
- Hook webhook URLs are validated for scheme/host.
- SDK distinguishes auth errors from request errors to avoid blind retries.

## Remaining Risks

- Webhook target trust is caller-defined; misconfigured URLs may leak payload data.
- Hook registrations are process-local and not cryptographically signed.

## Hardening Next Steps

- Persist webhook registrations with encryption-at-rest for secrets.
- Add webhook signature headers (HMAC) and replay protection.
- Add per-plugin rate limits and audit logging for trigger endpoints.
