# PromptMaster Completion Master Audit — 2026-09-17

Baseline for this audit: `ba6798b0f386528542dbda77d3b745ca1c977d7f` on `completion-audit-integration`.

This document freezes the completion audit before the final grouped hardening patches. It intentionally separates application defects from external release blockers.

## Release principle

A repository upload or static review is not a production release. Final GO requires the repository gates in `docs/RELEASE_GATES.md`, including real Django/PostgreSQL tests, migration drift, Docker builds, dependency audits, browser/security checks and external integration drills.

The current GitHub-hosted Actions blocker is external to application execution: affected jobs terminate with `runner_id: 0` and no steps. No workflow command is executed. This must be resolved before final production certification.

## Master Patch A — Identity / Tenant / RBAC / Sensitive Actions

### A1 — Cross-domain customer preview data

**Severity:** P1

`customers.read` currently allows customer detail/portal preview pages to expose license and order aggregates although the netstyle RBAC model intentionally separates `customers.read`, `licenses.read`, `orders.read`, `payments.read`, etc.

**Required fix:**
- Gate license aggregates behind `licenses.read`.
- Gate order aggregates behind `orders.read`.
- Keep member/device/customer metadata under `customers.read`, matching the existing permission model.
- Apply identically to company and private-customer detail/preview pages.
- Add negative RBAC tests proving values are absent when the domain permission is missing.

### A2 — Sensitive staff actions need one step-up policy

**Severity:** P1

The central password + completed-2FA re-auth gate currently protects support company-admin transfer only. Other high-impact internal actions must use the same policy instead of ad-hoc protection.

**Required coverage:**
- staff 2FA reset,
- staff activation/deactivation,
- staff role assignment / privilege changes,
- service-account token create/rotate/revoke,
- integration/payment secret changes,
- customer admin transfer (already protected).

Destructive or credential-changing actions must remain POST-only and permission-gated.

### A3 — Permission-domain consistency audit

**Severity:** P2

Dashboard/search/detail views must not expose data from a domain the staff identity cannot read. Payment-derived metrics must use the documented permission model consistently.

## Master Patch B — Commerce / Licensing / Payments / Concurrency

### B1 — Failed refund retry can reuse stale quote

**Severity:** P1

A refund is one-to-one with a license term. Reusing an existing `failed` refund currently risks retaining the old `remaining_days` and amount even when the retry occurs later.

**Required fix:**
- Recalculate the quote for every retry that is still legally/technically allowed.
- Never mutate submitted/succeeded refunds into a new quote.
- Preserve an auditable retry history or at minimum an attempt counter/timestamps.
- Add a regression test where a failed refund is retried on a later date and the amount decreases accordingly.

### B2 — Provider refund retry idempotency

**Severity:** P1

A permanently stable provider idempotency key for every retry can replay the original provider attempt instead of representing a new controlled retry.

**Required fix:** use a stable local refund identity plus attempt-specific provider idempotency while preserving local exactly-once state transitions.

### B3 — Assignment links must respect tenant suspension

**Severity:** P1

An assignment link issued before a company is disabled must no longer be consumable afterwards. Canonical assignment service logic must also reject inactive company tenants defensively.

### B4 — Existing protections to preserve

- paid order is terminal against stale/concurrent local writes,
- canonical provider state is re-fetched by webhook,
- amount/currency mismatch fails closed,
- activation is idempotent,
- seat assignment and device registration are serialized,
- device limit remains per user/product,
- Pro access remains server-side and entitlement/device/term checked.

## Master Patch C — Async / Privacy / Exports / Notifications / Ops

### C1 — Queued capability e-mails must revalidate the capability

**Severity:** P1

Broad user/company scope revalidation is insufficient for security links. Immediately before provider send:
- invitations must still be open, unexpired and belong to an active company,
- assignment links must still be unused, unrevoked, unexpired, target-bound and belong to an active company/current license context.

A revoked/consumed capability must never be delivered later from an old queue row.

### C2 — Company reminder recipient scope

**Severity:** P1

Company-license reminder rows must bind each queued e-mail to the concrete recipient user as well as the company. A former member/admin must not receive a reminder that was queued before removal.

### C3 — Notification regression suite

**Severity:** P1

The notifications app has no dedicated module test suite at the audit baseline. Add tests for capability revocation, membership removal, encrypted sensitive context, retry/claim behavior and idempotent reminder scheduling.

### C4 — Ops backup-status parsing must fail safe

**Severity:** P2

Malformed-but-valid JSON field types in backup status must generate a controlled unavailable/corrupt alert, not crash the alert refresh task.

### C5 — Existing export safeguards to preserve

Background exports already re-check authorization before materialization and before final publish; downloads are owner/permission/expiry/path constrained.

## Master Patch D — Prompt / MCP / Runtime / Studio

### D1 — Concurrent first publish

**Severity:** P1

Publishing two APPROVED versions concurrently when no published row exists must serialize on the PromptDefinition. The database unique constraint remains the final invariant, but an application race must produce a controlled lifecycle conflict rather than an uncaught IntegrityError/500.

### D2 — Active quality policy create race

**Severity:** P2

Concurrent first access must not race while creating the single active default PromptQualityPolicy.

### D3 — Regression coverage

Add PostgreSQL concurrency coverage for first publish and controlled conflict behavior. Preserve:
- one published version per definition,
- review/test gates,
- MCP read/draft/test-only allowlist,
- exact MCP service-account scopes,
- Pro API verified user + live entitlement + registered device contract.

## Master Patch E — Deployment / Backup / CI / Browser / Release

### E1 — Monitoring host privilege

**Severity:** P2 / explicit risk decision

cAdvisor currently runs privileged with host filesystem/runtime mounts. Keep it only if required and document the accepted host-level monitoring risk; otherwise reduce privileges/mounts to the minimum supported configuration.

### E2 — Backup/Ops status robustness

Keep `pg_dump -> restic -> restore drill` and harden status serialization/parsing so malformed status metadata cannot make health/alert logic fail silently.

### E3 — Release gate consolidation

After A–E:
1. repository/static validators,
2. shell syntax,
3. migration drift,
4. full Django/PostgreSQL suite including concurrency tests,
5. 100k DataGrid gate,
6. Docker builds and full-stack runtime validation,
7. dependency audits,
8. browser smokes,
9. Mollie/Graph/S3-restic external gates,
10. final human release review.

## External blocker — GitHub-hosted runners

Current and preceding workflow runs show jobs ending before step 1 with no allocated runner (`runner_id: 0`, empty steps). This is not evidence that application tests failed; it is also not evidence that they pass. Production certification stays blocked until real runners execute the gates.

## Definition of done

The completion branch is ready to merge only when:
- every P1 item above is fixed and regression-tested,
- P2 items are fixed or explicitly documented/accepted,
- all executable release gates actually run green,
- external provider/backup/browser gates are evidenced,
- no unresolved P0/P1 remains.
