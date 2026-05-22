---
name: security-best-practices
description: Practical secure-coding rules for auth, data handling, input validation, and defense-in-depth.
license: "See repository LICENSE"
user-invocable: false
---

# Security Best Practices

Use this skill for implementation or review when code touches trust boundaries, credentials, PII, authorization, uploads, payments, or external integrations.

## Priorities

1. **Least privilege**
2. **Validation at boundaries**
3. **Safe defaults**
4. **Secret hygiene**
5. **Auditability**

## Core Rules

### 1. Treat every external input as untrusted

Validate and normalize:

- request params
- headers
- bodies
- cookies
- files
- third-party payloads
- environment variables

Do not rely on frontend validation for security.

### 2. Keep authentication and authorization separate

- Authentication proves identity.
- Authorization proves permission for the конкретный action/resource.
- Always check authorization close to the business action, not only at the router edge.

### 3. Minimize secret exposure

- Never hardcode secrets.
- Keep secrets out of logs, client responses, screenshots, and test fixtures.
- Rotate and scope tokens/keys where the platform supports it.
- Prefer short-lived credentials when feasible.

### 4. Protect sensitive data deliberately

- Collect the minimum data needed.
- Encrypt or hash sensitive data where appropriate.
- Do not store passwords reversibly.
- Be explicit about retention, masking, and audit needs.

### 5. Prevent injection and unsafe execution

- Use parameterized queries.
- Avoid shell execution with interpolated user input.
- Validate file paths, URLs, and dynamic selectors before use.
- Normalize or reject untrusted structured objects before handing them to query builders or ORMs.

### 6. Fail safely

- Deny by default.
- Return safe, minimal error responses.
- Do not leak stack traces, internal IDs, provider payloads, or permission model details to untrusted clients.

### 7. Make side effects resistant to abuse

- Rate-limit abuse-prone endpoints.
- Add CSRF protection where relevant.
- Use idempotency or replay protection for sensitive write operations.
- Put sensible limits on uploads, payload size, and expensive operations.

## Review Heuristics

Look for:

- missing authz checks
- trust in client-supplied roles/flags
- secrets in source or logs
- unsafe file or command handling
- missing validation at service boundaries
- over-broad access to data or admin features
- internal error leakage
- retries or webhooks that can duplicate sensitive actions

## Common High-Risk Areas

- auth flows
- password reset / email verification
- payments and billing
- uploads and file parsing
- webhooks
- admin tools
- search/query builders
- any endpoint returning user-specific data

## Anti-Patterns

Avoid:

- "admin if flag says so" authorization
- passing raw provider payloads through the system unchecked
- logging tokens, passwords, card-like data, or full personal records
- broad catch blocks that convert security failures into generic success/fallback behavior
- storing long-lived secrets in client-accessible places

## Quick Checklist

- [ ] Inputs are validated at the boundary
- [ ] Auth and authz are both enforced
- [ ] Secrets are not exposed in code, logs, or responses
- [ ] Sensitive actions resist replay/abuse
- [ ] Error responses are safe
- [ ] Data exposure is limited to the minimum required
