# PromptMaster Completion Master Audit — 2026-09-17

Baseline for this audit: `ba6798b0f386528542dbda77d3b745ca1c977d7f` on `completion-audit-integration`.

This document freezes the completion audit and records the grouped hardening implementation. It intentionally separates application defects from external release blockers.

## Release principle

A repository upload or static review is not a production release. Final GO requires the repository gates in `docs/RELEASE_GATES.md`, including real Django/PostgreSQL tests, migration drift, Docker builds, dependency audits, browser/security checks and external integration drills.

The current GitHub-hosted Actions blocker is external to application execution: affected jobs terminate with `runner_id: 0` and no steps. No workflow command is executed. This must be resolved before final production certification.

## Master Patch A — Identity / Tenant / RBAC / Sensitive Actions

### A1 — Cross-domain customer preview data

**Severity:** P1 — **implemented**

`customers.read` no longer grants cross-domain license/order aggregates in company/private detail and portal-preview output. License data is gated by `licenses.read`; order data by `orders.read`. Customer/member/device metadata remains under the documented customer domain.

Regression coverage: `backend/apps/core/tests_master_patch_a.py`.

### A2 — Sensitive staff actions need one step-up policy

**Severity:** P1 — **implemented**

A central five-minute staff step-up grant now requires the user's password plus an already completed mandatory 2FA session. It protects staff identity/role changes, foreign 2FA reset, service-account credential operations, Mollie configuration, refunds, deletion execution and other high-impact actions. Customer-admin transfer retains its action-specific password + 2FA proof.

Destructive/credential-changing operations remain permission-gated and POST-only where applicable.

### A3 — Permission-domain consistency audit

**Severity:** P2 — **implemented**

Dashboard/search/detail output was aligned with domain capabilities; internal staff identities are not exposed through customer search without the role-read domain.

## Master Patch B — Commerce / Licensing / Payments / Concurrency

### B1 — Failed refund retry can reuse stale quote

**Severity:** P1 — **implemented**

A deterministic failed refund is requoted from the current remaining term before a new provider attempt. Submitted/ambiguous attempts retain their original quote until the provider outcome is known.

### B2 — Provider refund retry idempotency

**Severity:** P1 — **implemented**

`RefundAttempt` records preserve provider submission history. Deterministic failures may create a new attempt-specific idempotency key; network/5xx/invalid-success-body ambiguity reuses the exact active attempt/key. Success is terminal against stale concurrent local error responses.

A process interruption after provider success is recoverable: the periodic license-state task detects a locally successful refund whose term is not yet finalized and idempotently completes `mark_refund_success()`.

Regression coverage: `backend/apps/payments/tests_master_patch_b.py` including requote, ambiguity/idempotency, tenant suspension and interrupted-success recovery.

Migration: `backend/apps/payments/migrations/0003_refundattempt.py`; model/index names are explicitly pinned to the same migration state.

### B3 — Assignment links must respect tenant suspension

**Severity:** P1 — **implemented**

Canonical assignment/link/upgrade paths reject inactive company tenants. A link issued before tenant suspension cannot mutate license state after suspension.

### B4 — Existing protections preserved

- paid order remains terminal against stale/concurrent local writes,
- canonical provider state is re-fetched by webhook,
- amount/currency mismatch fails closed,
- activation remains idempotent,
- seat assignment and device registration remain serialized,
- device limit remains per user/product,
- Pro access remains server-side and entitlement/device/term checked.

## Master Patch C — Async / Privacy / Exports / Notifications / Ops

### C1 — Queued capability e-mails must revalidate the capability

**Severity:** P1 — **implemented**

Immediately before provider send, invite and assignment-link messages revalidate the concrete capability, not merely broad user/company scope. Revoked, consumed, expired, target-mismatched or tenant-invalid capabilities fail closed.

Sensitive URL/token context remains encrypted at rest.

### C2 — Company reminder recipient scope

**Severity:** P1 — **implemented**

Every company reminder is bound to the concrete current recipient user as well as the tenant. Queued reminders reconcile current recipients, so removed members/former admins are suppressed and replacement current recipients can be queued.

### C3 — Notification regression suite

**Severity:** P1 — **implemented**

Dedicated tests now cover capability revocation, encrypted sensitive context, membership removal, duplicate sender claim behavior and idempotent/current-recipient reminder scheduling.

Regression coverage: `backend/apps/notifications/tests_master_patch_c.py`.

### C4 — Ops backup-status parsing must fail safe

**Severity:** P2 — **implemented**

Status payloads must be JSON objects with valid bounded field types. Invalid objects, malformed numeric values and values outside PostgreSQL `BigInteger` range return controlled unavailable state instead of crashing alert refresh. Restore status receives equivalent shape validation.

Regression coverage: `backend/apps/ops/tests_master_patch_c.py`.

### C5 — Existing export safeguards preserved

Background exports continue to re-check authorization before materialization and final publish; downloads remain owner/permission/expiry/path constrained.

## Master Patch D — Prompt / MCP / Runtime / Studio

### D1 — Concurrent first publish

**Severity:** P1 — **implemented**

Publish now serializes on `PromptDefinition`, preserving the database unique constraint as the final invariant. Overlapping publish attempts produce a controlled lifecycle conflict rather than an uncaught unique-constraint error/500.

### D2 — Active quality policy create race

**Severity:** P2 — **implemented**

Concurrent first access to the default active quality policy is race-safe; a unique-constraint winner is resolved back to the canonical active policy rather than surfacing a 500.

### D3 — Regression coverage

PostgreSQL `TransactionTestCase` coverage exercises concurrent first publish and concurrent default-quality-policy creation in `backend/apps/prompts/tests_master_patch_d.py`.

Existing contracts remain unchanged:
- one published version per definition,
- review/test gates,
- MCP read/draft/test-only allowlist,
- exact MCP service-account scopes,
- Pro API verified user + live entitlement + registered device contract.

## Master Patch E — Deployment / Backup / CI / Browser / Release

### E1 — Monitoring host privilege

**Severity:** P2 — **explicitly documented risk decision**

cAdvisor remains a deliberately host-trusted monitoring component because removing `privileged`/host runtime access without a real staging metric test could silently destroy monitoring. Compensating controls and the mandatory acceptance/replacement gate are documented in `docs/RELEASE_GATES.md`: internal-only monitor network, no public cAdvisor/Prometheus port, read-only host mounts where supported, pinned image and host-impact incident assumption.

### E2 — Backup/Ops status robustness

**Severity:** P2 — **implemented**

The existing `pg_dump -> restic -> restore drill` design is preserved. Application-side status ingestion is fail-safe for malformed metadata and bounded to database field limits.

### E3 — Release gate consolidation

**Status:** **implemented; execution evidence externally blocked**

`docs/RELEASE_GATES.md` now consolidates:
1. repository/static validators,
2. shell syntax,
3. migration drift,
4. full Django/PostgreSQL suite including completion concurrency/security tests,
5. 100k DataGrid gate,
6. Docker builds and full-stack runtime validation,
7. dependency audits,
8. browser smokes,
9. Mollie/Graph/S3-restic external gates,
10. monitoring trust-boundary review and final human release review.

The existing `.github/workflows/ci.yml` already contains PostgreSQL/Redis, migration drift, full Django tests, 100k DataGrid, Docker/full-stack/restore and browser-smoke gates. Separate dependency-security and shell-syntax workflows remain authoritative for their domains.

## External blocker — GitHub-hosted runners

The current branch workflows still terminate before step 1 with no allocated GitHub-hosted runner (`runner_id: 0`, `steps: []`). On the current CI run all four jobs (`test`, `security`, `full-stack`, `browser-smoke`) were affected. This is not an application test failure and is also not pass evidence: no checkout, command, migration or test ran.

The available local execution environment for this audit also cannot resolve `github.com`, so it cannot clone the private branch as a substitute runner.

Therefore **production GO is not certified** until the same branch is executed on a real runner and the external provider/backup/browser gates are evidenced.

## Static completion status

After the grouped implementation and final cross-patch review:

- all P1 findings identified by this frozen audit have repository fixes and dedicated regression coverage;
- P2 application findings are fixed; the cAdvisor host privilege is converted into an explicit release-risk decision/gate;
- RefundAttempt model and migration index names are explicitly identical to avoid name-only migration drift;
- existing task return contracts were preserved while adding refund crash recovery;
- no additional unresolved P0/P1 was identified by the final static cross-patch review.

This statement is intentionally limited to static/code-level completion. Runtime correctness and production readiness remain gated by the unexecuted CI/staging/external gates.

## Definition of done

The implementation portion of A–E is complete. Merge/production readiness requires all of the following:
- every P1/P2 implementation above present in the branch,
- all executable release gates actually run green on a real runner,
- external provider/backup/browser gates evidenced,
- cAdvisor host-risk accepted or replaced after staging validation,
- final human review with no unresolved P0/P1.
