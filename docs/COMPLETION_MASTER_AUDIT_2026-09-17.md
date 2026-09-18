# PromptMaster Completion Master Audit — 2026-09-17

Baseline for this audit: `ba6798b0f386528542dbda77d3b745ca1c977d7f` on `completion-audit-integration`.

This document freezes the completion audit and records the grouped hardening implementation. It intentionally separates application defects from external release blockers.

## Release principle

A repository upload or static review is not a production release. Final GO requires the repository gates in `docs/RELEASE_GATES.md`, including real Django/PostgreSQL tests, migration drift, Docker builds, dependency audits, browser/security checks and external integration drills.

The historical GitHub-hosted runner allocation blocker has been resolved. Repository-controlled CI/runtime gates are executed on real runners and their current evidence is recorded below. External provider/infrastructure gates remain separate because they require real staging credentials and endpoints.

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

## Executed CI evidence — 2026-09-18

The repository-controlled completion state, including the hardened external-acceptance harnesses, is evidenced on commit `23a092fd5e6527867355644668351d7a23280dcd`, executed on real GitHub-hosted runners:

- **PromptMaster CI** — run `35335746672`: all four jobs green (`test`, `security`, `browser-smoke`, `full-stack`).
  - `test`: Marketing tests/lint/build, strict static repository guards, migration drift, migrations/seeds, Prompt runtime sanity, complete Django/PostgreSQL suite, external-acceptance safety/invariant regressions, 100k DataGrid, Compose validation, collectstatic and Docker builds.
  - `browser-smoke`: public auth/legal pages, customer portal, company-admin flows, private-customer admin flows, netstyle admin, Prompt Studio, tenant-safe searches, complete mobile navigation, responsive viewport coverage, overflow/overlap guards and Marketing browser smoke.
  - `full-stack`: clean bootstrap, production filesystem restrictions, monitoring/runtime validation, backup/restore failure propagation and recovery.
  - `security`: Python dependency audit and complete Marketing dependency audit.
- **PromptMaster Full Dependency Security** — run `35335746694`: green.
- **PromptMaster Shell Syntax** — run `35335746665`: green, including syntax validation and the explicit opt-in refusal guard for `scripts/external_backup_acceptance.sh`.

The external release harnesses are now executable and fail closed:
- **Mollie** accepts only `test_` API keys, uses the real portal checkout/provider/webhook/refund paths, requires provider/local status agreement and rejects false-green refund totals. Chargeback reversal may only pass when Mollie itself exposes a real reversed/provider-paid state and the corresponding webhook/business state is processed; local database manipulation is not accepted as evidence.
- **Microsoft Graph** uses the persisted production `EmailMessage`/task path, requires a real successful Graph send and additionally exercises a real provider failure with persisted retry/error state.
- **External S3/restic** requires an explicit confirmation value and an `s3:` target, proves that a new `promptmaster-db` snapshot ID was created, runs the isolated PostgreSQL restore/integrity check and requires a non-empty restore `backup_ref`.

These harnesses being implemented and repository-tested does **not** mark the external gates green. Mollie, Graph and external S3/restic still require execution in the actual staging/acceptance environment with real provider/infrastructure credentials. The cAdvisor monitoring functionality is runtime-validated; production still requires the explicit human acceptance (or separately validated replacement) of its documented host-level trust boundary.

## Static completion status

After the grouped implementation and final cross-patch review:

- all P1 findings identified by this frozen audit have repository fixes and dedicated regression coverage;
- P2 application findings are fixed; the cAdvisor host privilege is converted into an explicit release-risk decision/gate;
- RefundAttempt model and migration index names are explicitly identical to avoid name-only migration drift;
- existing task return contracts were preserved while adding refund crash recovery;
- no additional unresolved P0/P1 was identified by the final static cross-patch review.

Static/code-level completion and the repository-controlled CI/runtime gates are now evidenced on commit `23a092fd5e6527867355644668351d7a23280dcd`. Production readiness remains gated by execution/evidence of the real external provider/backup acceptance, explicit cAdvisor host-risk acceptance and final human release review.

## Definition of done

The implementation portion of A–E is complete, and all repository-controlled executable gates were green on the recorded code commit. Production readiness still requires all of the following:
- real Mollie Test-mode acceptance evidenced (purchase/webhook/refund/chargeback/reversal),
- real Microsoft Graph send + provider-failure acceptance evidenced,
- real external S3/restic backup + isolated PostgreSQL restore evidenced,
- cAdvisor host-risk explicitly accepted (monitoring functionality is already runtime-validated) or replaced only after separate staging validation,
- final human review with no unresolved P0/P1.
