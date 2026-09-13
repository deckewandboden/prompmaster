# AGENTS.md — Codex/Reviewer Contract

1. `SPEC.md` is the binding source of truth.
2. Never change license duration, reminder timing, device limit, tenant model, Mollie idempotency, RBAC, retention or API scopes without an explicit SPEC change.
3. Prefer fixes as small reviewed commits/PRs.
4. Before proposing a change run or reason through:
   - Django checks
   - migrations
   - unit/integration tests
   - permission/tenant isolation
   - N+1 queries
   - server-side pagination
   - webhook idempotency
   - transactions/race conditions
   - secret leakage
   - backup/restore implications
5. Never put production secrets into Git.
6. Never expose PostgreSQL, Redis, Prometheus or exporters publicly.
7. High-risk actions must be audited.
8. DataGrid list pages must preserve query state in URLs and show Reset when non-default state is active.
9. Customer and netstyle admin are separate surfaces; do not collapse them into one mega-page.
10. Human review is required before production merge/deploy.
